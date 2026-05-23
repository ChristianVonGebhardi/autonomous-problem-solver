package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"github.com/rs/cors"
)

type Server struct {
	db  *pgxpool.Pool
	nc  *nats.Conn
	js  nats.JetStreamContext
	rdb *redis.Client
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	ctx := context.Background()

	// PostgreSQL
	dbPool, err := pgxpool.New(ctx,
		getEnv("POSTGRES_DSN", "postgres://coordinator:coordinator_secret@localhost:5432/crcoordinator?sslmode=disable"))
	if err != nil {
		log.Fatalf("Failed to connect to postgres: %v", err)
	}
	defer dbPool.Close()

	// NATS (optional — API service mostly reads)
	var nc *nats.Conn
	var js nats.JetStreamContext
	if natsURL := getEnv("NATS_URL", ""); natsURL != "" {
		nc, err = connectNATSWithRetry(natsURL, 10)
		if err != nil {
			log.Printf("Warning: NATS unavailable, continuing without: %v", err)
		} else {
			js, _ = nc.JetStream()
			defer nc.Close()
		}
	}

	// Redis
	rdb := redis.NewClient(&redis.Options{
		Addr: getEnv("REDIS_URL", "localhost:6379"),
	})

	srv := &Server{db: dbPool, nc: nc, js: js, rdb: rdb}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestID)

	// CORS
	c := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Request-ID"},
		AllowCredentials: false,
	})
	r.Use(c.Handler)

	// ── Routes ──
	r.Get("/health", srv.handleHealth)

	r.Route("/api", func(r chi.Router) {
		// Metrics
		r.Get("/metrics", srv.handleMetrics)

		// Reviewers
		r.Get("/reviewers", srv.handleListReviewers)
		r.Post("/reviewers", srv.handleCreateReviewer)
		r.Get("/reviewers/stats", srv.handleReviewerStats)
		r.Get("/reviewers/{username}", srv.handleGetReviewer)
		r.Put("/reviewers/{username}/availability", srv.handleUpdateAvailability)

		// Pull Requests
		r.Get("/prs", srv.handleListPRs)
		r.Post("/prs", srv.handleCreatePR)
		r.Get("/prs/queue", srv.handleGetQueue)
		r.Get("/prs/{id}", srv.handleGetPR)
		r.Post("/prs/{id}/reassign", srv.handleReassignPR)
		r.Put("/prs/{id}/status", srv.handleUpdatePRStatus)

		// Events
		r.Get("/events", srv.handleGetEvents)

		// Assignments
		r.Get("/assignments", srv.handleGetAssignments)
	})

	addr := fmt.Sprintf(":%s", getEnv("PORT", "8085"))
	log.Printf("API service starting on %s", addr)
	if err := http.ListenAndServe(addr, r); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

// ── Health ─────────────────────────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	status := map[string]string{"status": "ok", "service": "api"}

	if err := s.db.Ping(ctx); err != nil {
		status["postgres"] = "error"
	} else {
		status["postgres"] = "ok"
	}

	if err := s.rdb.Ping(ctx).Err(); err != nil {
		status["redis"] = "error"
	} else {
		status["redis"] = "ok"
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

// ── Metrics ────────────────────────────────────────────────────────────────

func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	type MetricsOverview struct {
		ActivePRs             int      `json:"active_prs"`
		AvgTimeToAssignMin    float64  `json:"avg_time_to_assign_minutes"`
		AvgTimeToReviewMin    float64  `json:"avg_time_to_review_minutes"`
		AvgTimeToMergeHours   float64  `json:"avg_time_to_merge_hours"`
		PRsToday              int      `json:"prs_today"`
		PRsCompletedToday     int      `json:"prs_completed_today"`
		BottleneckReviewers   []string `json:"bottleneck_reviewers"`
	}

	m := MetricsOverview{}

	s.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM pull_requests WHERE state IN ('open','assigned','in_review')`).Scan(&m.ActivePRs)
	s.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM pull_requests WHERE created_at >= NOW() - INTERVAL '24 hours'`).Scan(&m.PRsToday)
	s.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM review_assignments WHERE completed_at >= NOW() - INTERVAL '24 hours'`).Scan(&m.PRsCompletedToday)
	s.db.QueryRow(ctx, `
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (ra.assigned_at - pr.created_at))/60), 0)
		FROM review_assignments ra
		JOIN pull_requests pr ON pr.id = ra.pr_id
		WHERE ra.assigned_at IS NOT NULL AND pr.created_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToAssignMin)
	s.db.QueryRow(ctx, `
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (ra.pickup_at - ra.assigned_at))/60), 0)
		FROM review_assignments ra
		WHERE ra.pickup_at IS NOT NULL AND ra.assigned_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToReviewMin)
	s.db.QueryRow(ctx, `
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (ra.completed_at - pr.created_at))/3600), 0)
		FROM review_assignments ra
		JOIN pull_requests pr ON pr.id = ra.pr_id
		WHERE ra.completed_at IS NOT NULL AND pr.created_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToMergeHours)

	// Bottleneck reviewers (at or over capacity)
	rows, err := s.db.Query(ctx, `
		SELECT r.username
		FROM reviewers r
		WHERE (
			SELECT COUNT(*) FROM review_assignments ra
			WHERE ra.reviewer_id = r.id AND ra.status IN ('pending','in_progress')
		) >= r.max_concurrent_reviews
		ORDER BY r.username LIMIT 5`)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var u string
			if rows.Scan(&u) == nil {
				m.BottleneckReviewers = append(m.BottleneckReviewers, u)
			}
		}
	}
	if m.BottleneckReviewers == nil {
		m.BottleneckReviewers = []string{}
	}

	// Queue length from Redis
	queueLen, _ := s.rdb.ZCard(ctx, "pr:queue:priority").Result()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"metrics":      m,
		"queue_length": queueLen,
		"timestamp":    time.Now().UTC(),
	})
}

// ── Reviewers ──────────────────────────────────────────────────────────────

type ReviewerRow struct {
	ID                  string    `json:"id"`
	Username            string    `json:"username"`
	DisplayName         string    `json:"display_name"`
	Email               string    `json:"email"`
	SlackUserID         string    `json:"slack_user_id"`
	Timezone            string    `json:"timezone"`
	MaxConcurrentReviews int      `json:"max_concurrent_reviews"`
	IsActive            bool      `json:"is_active"`
	ActiveReviews       int       `json:"current_load"`
	MaxLoad             int       `json:"max_load"`
	CreatedAt           time.Time `json:"created_at"`
}

func (s *Server) handleListReviewers(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := s.db.Query(ctx, `
		SELECT r.id, r.username, r.display_name, r.email, r.slack_user_id, r.timezone,
		       r.max_concurrent_reviews, r.is_active, r.created_at,
		       COUNT(ra.id) FILTER (WHERE ra.status IN ('pending','in_progress')) as active_reviews
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		GROUP BY r.id
		ORDER BY r.display_name`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var result []ReviewerRow
	for rows.Next() {
		var rv ReviewerRow
		err := rows.Scan(&rv.ID, &rv.Username, &rv.DisplayName, &rv.Email,
			&rv.SlackUserID, &rv.Timezone, &rv.MaxConcurrentReviews, &rv.IsActive,
			&rv.CreatedAt, &rv.ActiveReviews)
		if err != nil {
			continue
		}
		rv.MaxLoad = rv.MaxConcurrentReviews
		result = append(result, rv)
	}
	if result == nil {
		result = []ReviewerRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (s *Server) handleCreateReviewer(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req struct {
		Username    string `json:"username"`
		DisplayName string `json:"display_name"`
		Email       string `json:"email"`
		SlackUserID string `json:"slack_user_id"`
		Timezone    string `json:"timezone"`
		MaxReviews  int    `json:"max_concurrent_reviews"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}
	if req.Username == "" {
		http.Error(w, "username required", http.StatusBadRequest)
		return
	}
	if req.DisplayName == "" {
		req.DisplayName = req.Username
	}
	if req.Timezone == "" {
		req.Timezone = "UTC"
	}
	if req.MaxReviews == 0 {
		req.MaxReviews = 3
	}

	var id string
	err := s.db.QueryRow(ctx, `
		INSERT INTO reviewers (username, display_name, email, slack_user_id, timezone, max_concurrent_reviews)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT (username) DO UPDATE SET
			display_name = EXCLUDED.display_name,
			email = EXCLUDED.email,
			slack_user_id = EXCLUDED.slack_user_id,
			timezone = EXCLUDED.timezone,
			max_concurrent_reviews = EXCLUDED.max_concurrent_reviews,
			updated_at = NOW()
		RETURNING id`,
		req.Username, req.DisplayName, req.Email, req.SlackUserID, req.Timezone, req.MaxReviews,
	).Scan(&id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":       id,
		"username": req.Username,
		"status":   "created",
	})
}

func (s *Server) handleGetReviewer(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")
	ctx := r.Context()

	var rv ReviewerRow
	err := s.db.QueryRow(ctx, `
		SELECT r.id, r.username, r.display_name, r.email, r.slack_user_id, r.timezone,
		       r.max_concurrent_reviews, r.is_active, r.created_at,
		       COUNT(ra.id) FILTER (WHERE ra.status IN ('pending','in_progress')) as active_reviews
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		WHERE r.username = $1
		GROUP BY r.id`, username).
		Scan(&rv.ID, &rv.Username, &rv.DisplayName, &rv.Email,
			&rv.SlackUserID, &rv.Timezone, &rv.MaxConcurrentReviews, &rv.IsActive,
			&rv.CreatedAt, &rv.ActiveReviews)
	if err != nil {
		if err == pgx.ErrNoRows {
			http.Error(w, "reviewer not found", http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}
	rv.MaxLoad = rv.MaxConcurrentReviews

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rv)
}

func (s *Server) handleUpdateAvailability(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")
	ctx := r.Context()

	var req struct {
		IsActive bool `json:"is_active"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	_, err := s.db.Exec(ctx,
		`UPDATE reviewers SET is_active = $1, updated_at = NOW() WHERE username = $2`,
		req.IsActive, username)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"username": username, "is_active": req.IsActive})
}

func (s *Server) handleReviewerStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := s.db.Query(ctx, `
		SELECT
			r.username,
			COUNT(ra.id) FILTER (WHERE ra.status IN ('pending','in_progress')) as active_reviews,
			r.max_concurrent_reviews,
			COUNT(ra.id) FILTER (WHERE ra.completed_at >= NOW() - INTERVAL '24 hours') as completed_today,
			COALESCE(AVG(
				EXTRACT(EPOCH FROM (ra.completed_at - ra.assigned_at))/60
			) FILTER (WHERE ra.completed_at IS NOT NULL), 0) as avg_review_min
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		GROUP BY r.id
		ORDER BY active_reviews DESC`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type StatRow struct {
		Username        string  `json:"username"`
		ActiveReviews   int     `json:"active_reviews"`
		MaxReviews      int     `json:"max_reviews"`
		CompletedToday  int     `json:"completed_today"`
		AvgReviewMin    float64 `json:"avg_review_time_minutes"`
		UtilizationRate float64 `json:"utilization_rate"`
		IsBottleneck    bool    `json:"is_bottleneck"`
	}

	var stats []StatRow
	for rows.Next() {
		var st StatRow
		if err := rows.Scan(&st.Username, &st.ActiveReviews, &st.MaxReviews,
			&st.CompletedToday, &st.AvgReviewMin); err != nil {
			continue
		}
		if st.MaxReviews > 0 {
			st.UtilizationRate = float64(st.ActiveReviews) / float64(st.MaxReviews)
		}
		st.IsBottleneck = st.ActiveReviews >= st.MaxReviews
		stats = append(stats, st)
	}
	if stats == nil {
		stats = []StatRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}

// ── Pull Requests ──────────────────────────────────────────────────────────

type PRRow struct {
	ID              string    `json:"id"`
	ExternalID      string    `json:"external_id"`
	RepoFullName    string    `json:"repo_full_name"`
	Title           string    `json:"title"`
	Author          string    `json:"author"`
	State           string    `json:"status"`
	LinesAdded      int       `json:"lines_added"`
	LinesDeleted    int       `json:"lines_deleted"`
	FilesChanged    int       `json:"files_changed"`
	ComplexityScore *float64  `json:"complexity_score"`
	RiskScore       *float64  `json:"risk_score"`
	EstimatedMin    *int      `json:"estimated_minutes"`
	Priority        int       `json:"priority"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

func (s *Server) handleListPRs(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	state := r.URL.Query().Get("status")

	query := `SELECT id, external_id, repo_full_name, title, author_username, state,
		lines_added, lines_deleted, files_changed, complexity_score, risk_score,
		estimated_review_minutes, priority, created_at, updated_at
		FROM pull_requests`
	args := []interface{}{}
	if state != "" {
		query += ` WHERE state = $1`
		args = append(args, state)
	}
	query += ` ORDER BY priority DESC, created_at DESC LIMIT 100`

	rows, err := s.db.Query(ctx, query, args...)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var prs []PRRow
	for rows.Next() {
		var pr PRRow
		if err := rows.Scan(&pr.ID, &pr.ExternalID, &pr.RepoFullName, &pr.Title, &pr.Author,
			&pr.State, &pr.LinesAdded, &pr.LinesDeleted, &pr.FilesChanged,
			&pr.ComplexityScore, &pr.RiskScore, &pr.EstimatedMin, &pr.Priority,
			&pr.CreatedAt, &pr.UpdatedAt); err != nil {
			continue
		}
		prs = append(prs, pr)
	}
	if prs == nil {
		prs = []PRRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(prs)
}

func (s *Server) handleCreatePR(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req struct {
		ExternalID   string `json:"external_id"`
		RepoFullName string `json:"repo_full_name"`
		Title        string `json:"title"`
		Description  string `json:"description"`
		Author       string `json:"author"`
		LinesAdded   int    `json:"lines_added"`
		LinesDeleted int    `json:"lines_deleted"`
		FilesChanged int    `json:"files_changed"`
		Priority     int    `json:"priority"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}
	if req.Title == "" || req.Author == "" {
		http.Error(w, "title and author are required", http.StatusBadRequest)
		return
	}
	if req.Priority == 0 {
		req.Priority = 5
	}
	if req.RepoFullName == "" {
		req.RepoFullName = "demo/repo"
	}
	if req.ExternalID == "" {
		req.ExternalID = fmt.Sprintf("demo-%d", time.Now().UnixNano())
	}

	var id string
	err := s.db.QueryRow(ctx, `
		INSERT INTO pull_requests (external_id, repo_full_name, title, description,
			author_username, lines_added, lines_deleted, files_changed, priority)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
		RETURNING id`,
		req.ExternalID, req.RepoFullName, req.Title, req.Description,
		req.Author, req.LinesAdded, req.LinesDeleted, req.FilesChanged, req.Priority,
	).Scan(&id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Enqueue in Redis for routing
	s.rdb.ZAdd(ctx, "pr:queue:priority", redis.Z{
		Score:  float64(req.Priority),
		Member: id,
	})

	// Publish to NATS if available
	if s.js != nil {
		msg := map[string]interface{}{
			"pr_id":         id,
			"external_id":   req.ExternalID,
			"repo":          req.RepoFullName,
			"title":         req.Title,
			"author":        req.Author,
			"lines_added":   req.LinesAdded,
			"lines_deleted": req.LinesDeleted,
			"files_changed": req.FilesChanged,
			"action":        "opened",
		}
		msgBytes, _ := json.Marshal(msg)
		s.js.Publish("pr.events.new", msgBytes)
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]string{"id": id, "status": "created"})
}

func (s *Server) handleGetPR(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	ctx := r.Context()

	var pr PRRow
	err := s.db.QueryRow(ctx, `
		SELECT id, external_id, repo_full_name, title, author_username, state,
		lines_added, lines_deleted, files_changed, complexity_score, risk_score,
		estimated_review_minutes, priority, created_at, updated_at
		FROM pull_requests WHERE id = $1`, id).
		Scan(&pr.ID, &pr.ExternalID, &pr.RepoFullName, &pr.Title, &pr.Author,
			&pr.State, &pr.LinesAdded, &pr.LinesDeleted, &pr.FilesChanged,
			&pr.ComplexityScore, &pr.RiskScore, &pr.EstimatedMin, &pr.Priority,
			&pr.CreatedAt, &pr.UpdatedAt)
	if err != nil {
		if err == pgx.ErrNoRows {
			http.Error(w, "PR not found", http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}

	// Get assignments
	assignRows, _ := s.db.Query(ctx, `
		SELECT ra.id, rv.username, rv.display_name, ra.status, ra.assigned_at, ra.routing_reason, ra.score
		FROM review_assignments ra
		JOIN reviewers rv ON rv.id = ra.reviewer_id
		WHERE ra.pr_id = $1
		ORDER BY ra.assigned_at DESC`, id)

	type AssignRow struct {
		ID            string    `json:"id"`
		Username      string    `json:"username"`
		DisplayName   string    `json:"display_name"`
		Status        string    `json:"status"`
		AssignedAt    time.Time `json:"assigned_at"`
		RoutingReason string    `json:"routing_reason"`
		Score         float64   `json:"score"`
	}
	var assignments []AssignRow
	if assignRows != nil {
		defer assignRows.Close()
		for assignRows.Next() {
			var a AssignRow
			if err := assignRows.Scan(&a.ID, &a.Username, &a.DisplayName,
				&a.Status, &a.AssignedAt, &a.RoutingReason, &a.Score); err == nil {
				assignments = append(assignments, a)
			}
		}
	}
	if assignments == nil {
		assignments = []AssignRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"pr":          pr,
		"assignments": assignments,
	})
}

func (s *Server) handleReassignPR(w http.ResponseWriter, r *http.Request) {
	prID := chi.URLParam(r, "id")
	ctx := r.Context()

	var req struct {
		Reviewer string `json:"reviewer"`
		Reason   string `json:"reason"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}
	if req.Reviewer == "" {
		http.Error(w, "reviewer is required", http.StatusBadRequest)
		return
	}

	// Get reviewer ID
	var reviewerID string
	err := s.db.QueryRow(ctx, `SELECT id FROM reviewers WHERE username = $1`, req.Reviewer).Scan(&reviewerID)
	if err != nil {
		http.Error(w, "reviewer not found", http.StatusNotFound)
		return
	}

	// Mark existing assignments as reassigned
	s.db.Exec(ctx, `
		UPDATE review_assignments SET status = 'reassigned'
		WHERE pr_id = $1 AND status IN ('pending','in_progress')`, prID)

	// Create new assignment
	reason := req.Reason
	if reason == "" {
		reason = "Manual reassignment via dashboard"
	}
	var assignID string
	s.db.QueryRow(ctx, `
		INSERT INTO review_assignments (pr_id, reviewer_id, routing_reason, score)
		VALUES ($1, $2, $3, 0.5)
		RETURNING id`, prID, reviewerID, reason).Scan(&assignID)

	s.db.Exec(ctx, `UPDATE pull_requests SET state = 'assigned', updated_at = NOW() WHERE id = $1`, prID)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":   "reassigned",
		"reviewer": req.Reviewer,
	})
}

func (s *Server) handleUpdatePRStatus(w http.ResponseWriter, r *http.Request) {
	prID := chi.URLParam(r, "id")
	ctx := r.Context()

	var req struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	_, err := s.db.Exec(ctx,
		`UPDATE pull_requests SET state = $1, updated_at = NOW() WHERE id = $2`, req.Status, prID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
}

func (s *Server) handleGetQueue(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	rows, err := s.db.Query(ctx, `
		SELECT id, external_id, repo_full_name, title, author_username, state,
		lines_added, lines_deleted, files_changed, complexity_score, risk_score,
		estimated_review_minutes, priority, created_at, updated_at
		FROM pull_requests
		WHERE state IN ('open')
		ORDER BY priority DESC, created_at ASC
		LIMIT 50`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var prs []PRRow
	for rows.Next() {
		var pr PRRow
		if err := rows.Scan(&pr.ID, &pr.ExternalID, &pr.RepoFullName, &pr.Title, &pr.Author,
			&pr.State, &pr.LinesAdded, &pr.LinesDeleted, &pr.FilesChanged,
			&pr.ComplexityScore, &pr.RiskScore, &pr.EstimatedMin, &pr.Priority,
			&pr.CreatedAt, &pr.UpdatedAt); err != nil {
			continue
		}
		prs = append(prs, pr)
	}
	if prs == nil {
		prs = []PRRow{}
	}

	queueLen, _ := s.rdb.ZCard(ctx, "pr:queue:priority").Result()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"queue_length": queueLen,
		"prs":          prs,
	})
}

// ── Events ─────────────────────────────────────────────────────────────────

func (s *Server) handleGetEvents(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	rows, err := s.db.Query(ctx, `
		SELECT id, source, event_type, received_at, processed
		FROM webhook_events
		ORDER BY received_at DESC
		LIMIT 50`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type EventRow struct {
		ID         string    `json:"id"`
		Source     string    `json:"reviewer"`
		EventType  string    `json:"event_type"`
		ReceivedAt time.Time `json:"created_at"`
		Processed  bool      `json:"processed"`
	}

	var events []EventRow
	for rows.Next() {
		var e EventRow
		if err := rows.Scan(&e.ID, &e.Source, &e.EventType, &e.ReceivedAt, &e.Processed); err != nil {
			continue
		}
		events = append(events, e)
	}
	if events == nil {
		events = []EventRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(events)
}

// ── Assignments ────────────────────────────────────────────────────────────

func (s *Server) handleGetAssignments(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := s.db.Query(ctx, `
		SELECT
			ra.id, ra.pr_id, ra.assigned_at, ra.status,
			ra.routing_reason, ra.score,
			pr.title, pr.repo_full_name, pr.complexity_score, pr.risk_score,
			rv.username, rv.display_name
		FROM review_assignments ra
		JOIN pull_requests pr ON pr.id = ra.pr_id
		JOIN reviewers rv ON rv.id = ra.reviewer_id
		ORDER BY ra.assigned_at DESC
		LIMIT 50`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type AssignRow struct {
		ID              string    `json:"id"`
		PRID            string    `json:"pr_id"`
		AssignedAt      time.Time `json:"assigned_at"`
		Status          string    `json:"status"`
		RoutingReason   string    `json:"routing_reason"`
		Score           float64   `json:"score"`
		PRTitle         string    `json:"pr_title"`
		PRRepo          string    `json:"pr_repo"`
		ComplexityScore *float64  `json:"complexity_score"`
		RiskScore       *float64  `json:"risk_score"`
		Username        string    `json:"reviewer_username"`
		DisplayName     string    `json:"reviewer_name"`
	}

	var assignments []AssignRow
	for rows.Next() {
		var a AssignRow
		if err := rows.Scan(&a.ID, &a.PRID, &a.AssignedAt, &a.Status,
			&a.RoutingReason, &a.Score, &a.PRTitle, &a.PRRepo,
			&a.ComplexityScore, &a.RiskScore, &a.Username, &a.DisplayName); err != nil {
			log.Printf("scan: %v", err)
			continue
		}
		assignments = append(assignments, a)
	}
	if assignments == nil {
		assignments = []AssignRow{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(assignments)
}

// ── Helpers ────────────────────────────────────────────────────────────────

func connectNATSWithRetry(url string, maxRetries int) (*nats.Conn, error) {
	var nc *nats.Conn
	var err error
	for i := 0; i < maxRetries; i++ {
		nc, err = nats.Connect(url)
		if err == nil {
			return nc, nil
		}
		log.Printf("NATS connection attempt %d failed: %v", i+1, err)
		time.Sleep(2 * time.Second)
	}
	return nil, fmt.Errorf("failed after %d attempts: %w", maxRetries, err)
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}