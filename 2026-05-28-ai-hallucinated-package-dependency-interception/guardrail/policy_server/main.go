// GuardRail Policy Server
//
// A lightweight HTTP service for team-level allow/block lists and risk thresholds.
// Deploy as a single binary or Docker container.
//
// Usage:
//   go build -o guardrail-policy .
//   ./guardrail-policy --port 8080 --db policy.db
//
// API:
//   GET  /api/v1/policy/check?package=NAME&ecosystem=pypi
//   POST /api/v1/policy/rules
//   GET  /api/v1/policy/rules
//   DELETE /api/v1/policy/rules/{id}
//   GET  /health

package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// ─── Models ───────────────────────────────────────────────────────────────────

type PolicyRule struct {
	ID          int64     `json:"id"`
	PackageName string    `json:"package_name"`
	Ecosystem   string    `json:"ecosystem"`
	Action      string    `json:"action"` // "allow" | "block"
	Reason      string    `json:"reason"`
	CreatedBy   string    `json:"created_by"`
	CreatedAt   time.Time `json:"created_at"`
	IsGlob      bool      `json:"is_glob"` // if true, package_name is a glob pattern
}

type PolicyCheckResponse struct {
	Package   string  `json:"package"`
	Ecosystem string  `json:"ecosystem"`
	Action    *string `json:"action"` // null = no policy, "allow" | "block"
	RuleID    *int64  `json:"rule_id,omitempty"`
	Reason    string  `json:"reason,omitempty"`
}

type CreateRuleRequest struct {
	PackageName string `json:"package_name"`
	Ecosystem   string `json:"ecosystem"`
	Action      string `json:"action"`
	Reason      string `json:"reason"`
	CreatedBy   string `json:"created_by"`
	IsGlob      bool   `json:"is_glob"`
}

type Config struct {
	Port   int
	DBPath string
	APIKey string // optional; if set, require X-API-Key header
}

// ─── Server ───────────────────────────────────────────────────────────────────

type Server struct {
	db  *sql.DB
	cfg Config
}

func NewServer(cfg Config) (*Server, error) {
	db, err := sql.Open("sqlite3", cfg.DBPath)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}

	s := &Server{db: db, cfg: cfg}
	if err := s.initDB(); err != nil {
		return nil, fmt.Errorf("init db: %w", err)
	}
	return s, nil
}

func (s *Server) initDB() error {
	_, err := s.db.Exec(`
		CREATE TABLE IF NOT EXISTS policy_rules (
			id           INTEGER PRIMARY KEY AUTOINCREMENT,
			package_name TEXT    NOT NULL,
			ecosystem    TEXT    NOT NULL,
			action       TEXT    NOT NULL CHECK(action IN ('allow','block')),
			reason       TEXT    NOT NULL DEFAULT '',
			created_by   TEXT    NOT NULL DEFAULT '',
			created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			is_glob      INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX IF NOT EXISTS idx_rules_pkg ON policy_rules(ecosystem, package_name);
	`)
	return err
}

// ─── Middleware ───────────────────────────────────────────────────────────────

func (s *Server) authMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.APIKey != "" {
			key := r.Header.Get("X-API-Key")
			if key != s.cfg.APIKey {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
		}
		next(w, r)
	}
}

func (s *Server) jsonMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-GuardRail-Version", "0.1.0")
		next(w, r)
	}
}

func (s *Server) loggingMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next(w, r)
		log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start))
	}
}

func chain(h http.HandlerFunc, middlewares ...func(http.HandlerFunc) http.HandlerFunc) http.HandlerFunc {
	for i := len(middlewares) - 1; i >= 0; i-- {
		h = middlewares[i](h)
	}
	return h
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"version": "0.1.0",
		"time":    time.Now().UTC(),
	})
}

func (s *Server) handlePolicyCheck(w http.ResponseWriter, r *http.Request) {
	pkg := strings.TrimSpace(r.URL.Query().Get("package"))
	ecosystem := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("ecosystem")))

	if pkg == "" || ecosystem == "" {
		http.Error(w, `{"error":"package and ecosystem are required"}`, http.StatusBadRequest)
		return
	}

	// Check exact match first
	var rule PolicyRule
	err := s.db.QueryRow(`
		SELECT id, package_name, ecosystem, action, reason, created_by, created_at, is_glob
		FROM policy_rules
		WHERE ecosystem = ? AND package_name = ? AND is_glob = 0
		ORDER BY id DESC LIMIT 1
	`, ecosystem, pkg).Scan(
		&rule.ID, &rule.PackageName, &rule.Ecosystem,
		&rule.Action, &rule.Reason, &rule.CreatedBy,
		&rule.CreatedAt, &rule.IsGlob,
	)

	if err == nil {
		action := rule.Action
		resp := PolicyCheckResponse{
			Package:   pkg,
			Ecosystem: ecosystem,
			Action:    &action,
			RuleID:    &rule.ID,
			Reason:    rule.Reason,
		}
		json.NewEncoder(w).Encode(resp)
		return
	}

	if err != sql.ErrNoRows {
		http.Error(w, `{"error":"database error"}`, http.StatusInternalServerError)
		return
	}

	// Check glob patterns
	rows, err := s.db.Query(`
		SELECT id, package_name, ecosystem, action, reason, created_by, created_at, is_glob
		FROM policy_rules
		WHERE ecosystem = ? AND is_glob = 1
		ORDER BY id DESC
	`, ecosystem)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var gr PolicyRule
			if err := rows.Scan(
				&gr.ID, &gr.PackageName, &gr.Ecosystem,
				&gr.Action, &gr.Reason, &gr.CreatedBy,
				&gr.CreatedAt, &gr.IsGlob,
			); err != nil {
				continue
			}
			if matchGlob(gr.PackageName, pkg) {
				action := gr.Action
				resp := PolicyCheckResponse{
					Package:   pkg,
					Ecosystem: ecosystem,
					Action:    &action,
					RuleID:    &gr.ID,
					Reason:    gr.Reason,
				}
				json.NewEncoder(w).Encode(resp)
				return
			}
		}
	}

	// No policy found
	resp := PolicyCheckResponse{
		Package:   pkg,
		Ecosystem: ecosystem,
		Action:    nil,
	}
	json.NewEncoder(w).Encode(resp)
}

func (s *Server) handleListRules(w http.ResponseWriter, r *http.Request) {
	ecosystem := r.URL.Query().Get("ecosystem")
	action := r.URL.Query().Get("action")

	query := `SELECT id, package_name, ecosystem, action, reason, created_by, created_at, is_glob FROM policy_rules WHERE 1=1`
	args := []interface{}{}

	if ecosystem != "" {
		query += " AND ecosystem = ?"
		args = append(args, ecosystem)
	}
	if action != "" {
		query += " AND action = ?"
		args = append(args, action)
	}
	query += " ORDER BY id DESC LIMIT 500"

	rows, err := s.db.Query(query, args...)
	if err != nil {
		http.Error(w, `{"error":"database error"}`, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	rules := []PolicyRule{}
	for rows.Next() {
		var rule PolicyRule
		if err := rows.Scan(
			&rule.ID, &rule.PackageName, &rule.Ecosystem,
			&rule.Action, &rule.Reason, &rule.CreatedBy,
			&rule.CreatedAt, &rule.IsGlob,
		); err != nil {
			continue
		}
		rules = append(rules, rule)
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"rules": rules,
		"total": len(rules),
	})
}

func (s *Server) handleCreateRule(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var req CreateRuleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid JSON body"}`, http.StatusBadRequest)
		return
	}

	// Validate
	req.PackageName = strings.TrimSpace(req.PackageName)
	req.Ecosystem = strings.ToLower(strings.TrimSpace(req.Ecosystem))
	req.Action = strings.ToLower(strings.TrimSpace(req.Action))

	if req.PackageName == "" {
		http.Error(w, `{"error":"package_name is required"}`, http.StatusBadRequest)
		return
	}
	if req.Ecosystem == "" {
		http.Error(w, `{"error":"ecosystem is required"}`, http.StatusBadRequest)
		return
	}
	if req.Action != "allow" && req.Action != "block" {
		http.Error(w, `{"error":"action must be 'allow' or 'block'"}`, http.StatusBadRequest)
		return
	}

	isGlob := 0
	if req.IsGlob {
		isGlob = 1
	}

	result, err := s.db.Exec(`
		INSERT INTO policy_rules (package_name, ecosystem, action, reason, created_by, is_glob)
		VALUES (?, ?, ?, ?, ?, ?)
	`, req.PackageName, req.Ecosystem, req.Action, req.Reason, req.CreatedBy, isGlob)
	if err != nil {
		http.Error(w, `{"error":"database error"}`, http.StatusInternalServerError)
		return
	}

	id, _ := result.LastInsertId()
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":      id,
		"message": "rule created",
	})
}

func (s *Server) handleDeleteRule(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	// Extract ID from path: /api/v1/policy/rules/{id}
	parts := strings.Split(r.URL.Path, "/")
	if len(parts) == 0 {
		http.Error(w, `{"error":"missing rule id"}`, http.StatusBadRequest)
		return
	}
	idStr := parts[len(parts)-1]
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		http.Error(w, `{"error":"invalid rule id"}`, http.StatusBadRequest)
		return
	}

	result, err := s.db.Exec("DELETE FROM policy_rules WHERE id = ?", id)
	if err != nil {
		http.Error(w, `{"error":"database error"}`, http.StatusInternalServerError)
		return
	}

	affected, _ := result.RowsAffected()
	if affected == 0 {
		http.Error(w, `{"error":"rule not found"}`, http.StatusNotFound)
		return
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"message": "rule deleted",
		"id":      id,
	})
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// matchGlob performs simple glob matching (* = any sequence).
func matchGlob(pattern, name string) bool {
	// Convert * to split and check prefix/suffix/contains
	if pattern == "*" {
		return true
	}
	if !strings.Contains(pattern, "*") {
		return pattern == name
	}

	parts := strings.Split(pattern, "*")
	if len(parts) == 2 {
		prefix, suffix := parts[0], parts[1]
		if len(prefix) > 0 && !strings.HasPrefix(name, prefix) {
			return false
		}
		if len(suffix) > 0 && !strings.HasSuffix(name, suffix) {
			return false
		}
		return true
	}

	// Multi-wildcard: check each segment is contained in order
	pos := 0
	for _, part := range parts {
		if part == "" {
			continue
		}
		idx := strings.Index(name[pos:], part)
		if idx < 0 {
			return false
		}
		pos += idx + len(part)
	}
	return true
}

// ─── Main ─────────────────────────────────────────────────────────────────────

func main() {
	cfg := Config{
		Port:   8080,
		DBPath: "policy.db",
		APIKey: os.Getenv("GUARDRAIL_API_KEY"),
	}

	if portStr := os.Getenv("PORT"); portStr != "" {
		if p, err := strconv.Atoi(portStr); err == nil {
			cfg.Port = p
		}
	}
	if dbPath := os.Getenv("GUARDRAIL_DB"); dbPath != "" {
		cfg.DBPath = dbPath
	}

	// Parse CLI args
	for i, arg := range os.Args[1:] {
		switch {
		case arg == "--port" && i+1 < len(os.Args[1:]):
			if p, err := strconv.Atoi(os.Args[i+2]); err == nil {
				cfg.Port = p
			}
		case arg == "--db" && i+1 < len(os.Args[1:]):
			cfg.DBPath = os.Args[i+2]
		case arg == "--api-key" && i+1 < len(os.Args[1:]):
			cfg.APIKey = os.Args[i+2]
		case strings.HasPrefix(arg, "--port="):
			if p, err := strconv.Atoi(strings.TrimPrefix(arg, "--port=")); err == nil {
				cfg.Port = p
			}
		case strings.HasPrefix(arg, "--db="):
			cfg.DBPath = strings.TrimPrefix(arg, "--db=")
		}
	}

	server, err := NewServer(cfg)
	if err != nil {
		log.Fatalf("Failed to start policy server: %v", err)
	}

	mux := http.NewServeMux()

	mw := []func(http.HandlerFunc) http.HandlerFunc{
		server.loggingMiddleware,
		server.jsonMiddleware,
	}
	authMW := []func(http.HandlerFunc) http.HandlerFunc{
		server.loggingMiddleware,
		server.jsonMiddleware,
		server.authMiddleware,
	}

	mux.HandleFunc("/health", chain(server.handleHealth, mw...))
	mux.HandleFunc("/api/v1/policy/check", chain(server.handlePolicyCheck, mw...))
	mux.HandleFunc("/api/v1/policy/rules", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.Method {
		case http.MethodGet:
			chain(server.handleListRules, authMW...)(w, r)
		case http.MethodPost:
			chain(server.handleCreateRule, authMW...)(w, r)
		default:
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		}
	})
	mux.HandleFunc("/api/v1/policy/rules/", chain(server.handleDeleteRule, authMW...))

	addr := fmt.Sprintf(":%d", cfg.Port)
	log.Printf("GuardRail Policy Server v0.1.0 listening on %s", addr)
	log.Printf("Database: %s", cfg.DBPath)
	if cfg.APIKey != "" {
		log.Printf("API key authentication enabled")
	} else {
		log.Printf("WARNING: No API key configured — running in unauthenticated mode")
	}

	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}