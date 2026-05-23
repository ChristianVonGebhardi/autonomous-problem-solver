package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

type WebhookEvent struct {
	ID          string          `json:"id"`
	Source      string          `json:"source"`
	EventType   string          `json:"event_type"`
	Payload     json.RawMessage `json:"payload"`
	ReceivedAt  time.Time       `json:"received_at"`
}

type PREvent struct {
	Action      string `json:"action"`
	PR          PRData `json:"pull_request"`
	Repository  RepoData `json:"repository"`
}

type PRData struct {
	Number    int    `json:"number"`
	Title     string `json:"title"`
	Body      string `json:"body"`
	HTMLURL   string `json:"html_url"`
	State     string `json:"state"`
	User      UserData `json:"user"`
	Base      BranchData `json:"base"`
	Head      BranchData `json:"head"`
	Additions int    `json:"additions"`
	Deletions int    `json:"deletions"`
	ChangedFiles int `json:"changed_files"`
	CreatedAt time.Time `json:"created_at"`
	Labels    []LabelData `json:"labels"`
}

type UserData struct {
	Login string `json:"login"`
}

type BranchData struct {
	Ref string `json:"ref"`
}

type RepoData struct {
	FullName string `json:"full_name"`
}

type LabelData struct {
	Name string `json:"name"`
}

type Server struct {
	db     *pgxpool.Pool
	nc     *nats.Conn
	js     nats.JetStreamContext
	rdb    *redis.Client
	secret string
}

func main() {
	ctx := context.Background()

	// Database
	dbPool, err := pgxpool.New(ctx, getEnv("POSTGRES_DSN", "postgres://coordinator:coordinator_secret@localhost:5432/crcoordinator?sslmode=disable"))
	if err != nil {
		log.Fatalf("Failed to connect to postgres: %v", err)
	}
	defer dbPool.Close()

	// NATS
	nc, err := connectNATSWithRetry(getEnv("NATS_URL", "nats://localhost:4222"), 15)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()

	js, err := nc.JetStream()
	if err != nil {
		log.Fatalf("Failed to get JetStream: %v", err)
	}

	// Create streams
	setupStreams(js)

	// Redis
	rdb := redis.NewClient(&redis.Options{
		Addr: getEnv("REDIS_URL", "localhost:6379"),
	})

	srv := &Server{
		db:     dbPool,
		nc:     nc,
		js:     js,
		rdb:    rdb,
		secret: getEnv("WEBHOOK_SECRET", "dev_webhook_secret_123"),
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))

	r.Get("/health", srv.handleHealth)
	r.Post("/webhooks/github", srv.handleGitHubWebhook)
	r.Post("/webhooks/gitlab", srv.handleGitLabWebhook)
	r.Post("/webhooks/simulate", srv.handleSimulateWebhook) // For testing

	log.Println("Ingestion service starting on :8080")
	if err := http.ListenAndServe(":8080", r); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func connectNATSWithRetry(url string, maxRetries int) (*nats.Conn, error) {
	var nc *nats.Conn
	var err error
	for i := 0; i < maxRetries; i++ {
		nc, err = nats.Connect(url)
		if err == nil {
			return nc, nil
		}
		log.Printf("NATS connection attempt %d failed: %v, retrying...", i+1, err)
		time.Sleep(2 * time.Second)
	}
	return nil, fmt.Errorf("failed after %d attempts: %w", maxRetries, err)
}

func setupStreams(js nats.JetStreamContext) {
	streams := []struct {
		name     string
		subjects []string
	}{
		{"PR_EVENTS", []string{"pr.events.>"}},
		{"PR_ANALYZED", []string{"pr.analyzed.>"}},
		{"PR_ASSIGNED", []string{"pr.assigned.>"}},
	}

	for _, s := range streams {
		_, err := js.StreamInfo(s.name)
		if err != nil {
			_, err = js.AddStream(&nats.StreamConfig{
				Name:     s.name,
				Subjects: s.subjects,
				Storage:  nats.FileStorage,
				MaxAge:   24 * time.Hour,
			})
			if err != nil {
				log.Printf("Warning: failed to create stream %s: %v", s.name, err)
			} else {
				log.Printf("Created NATS stream: %s", s.name)
			}
		}
	}
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	status := map[string]string{"status": "ok", "service": "ingestion"}

	if err := s.db.Ping(ctx); err != nil {
		status["postgres"] = "error: " + err.Error()
	} else {
		status["postgres"] = "ok"
	}

	if err := s.rdb.Ping(ctx).Err(); err != nil {
		status["redis"] = "error: " + err.Error()
	} else {
		status["redis"] = "ok"
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func (s *Server) handleGitHubWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}

	// Verify signature
	sig := r.Header.Get("X-Hub-Signature-256")
	if sig != "" && !s.verifyGitHubSignature(body, sig) {
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}

	eventType := r.Header.Get("X-GitHub-Event")
	if eventType == "" {
		eventType = "push"
	}

	event := WebhookEvent{
		ID:         uuid.New().String(),
		Source:     "github",
		EventType:  eventType,
		Payload:    json.RawMessage(body),
		ReceivedAt: time.Now(),
	}

	if err := s.processWebhookEvent(r.Context(), event); err != nil {
		log.Printf("Error processing webhook: %v", err)
		http.Error(w, "Processing error", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{"status": "accepted", "id": event.ID})
}

func (s *Server) handleGitLabWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}

	eventType := r.Header.Get("X-Gitlab-Event")

	event := WebhookEvent{
		ID:         uuid.New().String(),
		Source:     "gitlab",
		EventType:  eventType,
		Payload:    json.RawMessage(body),
		ReceivedAt: time.Now(),
	}

	if err := s.processWebhookEvent(r.Context(), event); err != nil {
		log.Printf("Error processing webhook: %v", err)
		http.Error(w, "Processing error", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{"status": "accepted", "id": event.ID})
}

// handleSimulateWebhook allows testing without a real GitHub instance
func (s *Server) handleSimulateWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}

	event := WebhookEvent{
		ID:         uuid.New().String(),
		Source:     "github",
		EventType:  "pull_request",
		Payload:    json.RawMessage(body),
		ReceivedAt: time.Now(),
	}

	if err := s.processWebhookEvent(r.Context(), event); err != nil {
		log.Printf("Error processing simulated webhook: %v", err)
		http.Error(w, "Processing error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{"status": "accepted", "id": event.ID})
}

func (s *Server) processWebhookEvent(ctx context.Context, event WebhookEvent) error {
	// Store raw event
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}

	_, err = s.db.Exec(ctx, `
		INSERT INTO webhook_events (id, source, event_type, payload, received_at)
		VALUES ($1, $2, $3, $4, $5)`,
		event.ID, event.Source, event.EventType, event.Payload, event.ReceivedAt,
	)
	if err != nil {
		log.Printf("Warning: failed to store webhook event: %v", err)
	}

	// Only process PR events
	if event.EventType != "pull_request" && event.EventType != "Merge Request Hook" {
		return nil
	}

	// Parse PR event
	var prEvent PREvent
	if err := json.Unmarshal(event.Payload, &prEvent); err != nil {
		return fmt.Errorf("parse PR event: %w", err)
	}

	// Only process opened/synchronize/reopened actions
	if prEvent.Action != "opened" && prEvent.Action != "synchronize" && prEvent.Action != "reopened" && prEvent.Action != "" {
		log.Printf("Skipping PR action: %s", prEvent.Action)
		return nil
	}

	// Extract labels
	labels := make([]string, len(prEvent.PR.Labels))
	for i, l := range prEvent.PR.Labels {
		labels[i] = l.Name
	}

	// Calculate priority from labels
	priority := 5
	for _, l := range labels {
		if strings.Contains(strings.ToLower(l), "urgent") || strings.Contains(strings.ToLower(l), "hotfix") {
			priority = 9
		} else if strings.Contains(strings.ToLower(l), "high") {
			priority = 7
		} else if strings.Contains(strings.ToLower(l), "low") {
			priority = 3
		}
	}

	externalID := fmt.Sprintf("%d", prEvent.PR.Number)
	repoName := prEvent.Repository.FullName
	if repoName == "" {
		repoName = "unknown/repo"
	}

	// Upsert PR
	var prID string
	err = s.db.QueryRow(ctx, `
		INSERT INTO pull_requests (
			external_id, repo_full_name, title, description, author_username,
			vcs_type, pr_url, base_branch, head_branch, state,
			lines_added, lines_deleted, files_changed, priority, labels,
			vcs_created_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'open',$10,$11,$12,$13,$14,$15)
		ON CONFLICT (external_id, repo_full_name) DO UPDATE SET
			title = EXCLUDED.title,
			lines_added = EXCLUDED.lines_added,
			lines_deleted = EXCLUDED.lines_deleted,
			files_changed = EXCLUDED.files_changed,
			updated_at = NOW()
		RETURNING id`,
		externalID, repoName, prEvent.PR.Title, prEvent.PR.Body,
		prEvent.PR.User.Login, event.Source, prEvent.PR.HTMLURL,
		prEvent.PR.Base.Ref, prEvent.PR.Head.Ref,
		prEvent.PR.Additions, prEvent.PR.Deletions, prEvent.PR.ChangedFiles,
		priority, labels, prEvent.PR.CreatedAt,
	).Scan(&prID)
	if err != nil {
		return fmt.Errorf("upsert PR: %w", err)
	}

	// Publish to NATS for analysis
	msg := map[string]interface{}{
		"pr_id":       prID,
		"external_id": externalID,
		"repo":        repoName,
		"action":      prEvent.Action,
		"source":      event.Source,
		"lines_added": prEvent.PR.Additions,
		"lines_deleted": prEvent.PR.Deletions,
		"files_changed": prEvent.PR.ChangedFiles,
		"title":       prEvent.PR.Title,
		"author":      prEvent.PR.User.Login,
	}

	msgBytes, _ := json.Marshal(msg)
	_, err = s.js.Publish("pr.events.new", msgBytes)
	if err != nil {
		log.Printf("Warning: failed to publish to NATS: %v", err)
	}

	// Cache in Redis
	s.rdb.Set(ctx, fmt.Sprintf("pr:queue:%s", prID), "pending", 24*time.Hour)
	s.rdb.ZAdd(ctx, "pr:queue:priority", redis.Z{
		Score:  float64(priority),
		Member: prID,
	})

	log.Printf("Ingested PR %s (repo: %s, priority: %d)", prID, repoName, priority)

	// Mark webhook as processed
	s.db.Exec(ctx, `UPDATE webhook_events SET processed = true, processed_at = NOW() WHERE id = $1`, event.ID)

	return nil
}

func (s *Server) verifyGitHubSignature(body []byte, signature string) bool {
	if !strings.HasPrefix(signature, "sha256=") {
		return false
	}
	mac := hmac.New(sha256.New, []byte(s.secret))
	mac.Write(body)
	expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(signature))
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}