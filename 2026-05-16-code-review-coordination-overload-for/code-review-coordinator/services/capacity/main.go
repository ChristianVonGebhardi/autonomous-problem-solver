package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

type ReviewerStatus struct {
	ReviewerID      string    `json:"reviewer_id"`
	Username        string    `json:"username"`
	DisplayName     string    `json:"display_name"`
	ActiveReviews   int       `json:"active_reviews"`
	PendingReviews  int       `json:"pending_reviews"`
	MaxReviews      int       `json:"max_reviews"`
	CapacityScore   float64   `json:"capacity_score"`
	IsAvailable     bool      `json:"is_available"`
	UpdatedAt       time.Time `json:"updated_at"`
}

type ReviewEvent struct {
	Type        string `json:"type"` // started, completed, reassigned
	AssignmentID string `json:"assignment_id"`
	ReviewerID  string `json:"reviewer_id"`
	PRID        string `json:"pr_id"`
	Timestamp   time.Time `json:"timestamp"`
}

type Server struct {
	db  *pgxpool.Pool
	nc  *nats.Conn
	js  nats.JetStreamContext
	rdb *redis.Client
}

func main() {
	ctx := context.Background()

	dbPool, err := pgxpool.New(ctx, getEnv("POSTGRES_DSN", "postgres://coordinator:coordinator_secret@localhost:5432/crcoordinator?sslmode=disable"))
	if err != nil {
		log.Fatalf("Failed to connect to postgres: %v", err)
	}
	defer dbPool.Close()

	nc, err := connectNATSWithRetry(getEnv("NATS_URL", "nats://localhost:4222"), 15)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()

	js, err := nc.JetStream()
	if err != nil {
		log.Fatalf("Failed to get JetStream: %v", err)
	}

	rdb := redis.NewClient(&redis.Options{
		Addr: getEnv("REDIS_URL", "localhost:6379"),
	})

	srv := &Server{db: dbPool, nc: nc, js: js, rdb: rdb}

	// Start background jobs
	go srv.syncCapacityLoop(ctx)
	go srv.subscribeReviewEvents()

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", srv.handleHealth)
	r.Get("/capacity", srv.handleGetCapacity)
	r.Get("/capacity/{reviewer_id}", srv.handleGetReviewerCapacity)
	r.Post("/reviews/{assignment_id}/start", srv.handleStartReview)
	r.Post("/reviews/{assignment_id}/complete", srv.handleCompleteReview)

	log.Println("Capacity tracker starting on :8084")
	if err := http.ListenAndServe(":8084", r); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func (s *Server) syncCapacityLoop(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	// Initial sync
	s.syncAllCapacity(ctx)

	for {
		select {
		case <-ticker.C:
			s.syncAllCapacity(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func (s *Server) syncAllCapacity(ctx context.Context) {
	rows, err := s.db.Query(ctx, `
		SELECT 
			r.id, r.username, r.display_name, r.max_concurrent_reviews,
			COUNT(ra.id) FILTER (WHERE ra.status = 'in_progress') as active,
			COUNT(ra.id) FILTER (WHERE ra.status = 'pending') as pending
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		WHERE r.is_active = true
		GROUP BY r.id, r.username, r.display_name, r.max_concurrent_reviews`)
	if err != nil {
		log.Printf("Failed to sync capacity: %v", err)
		return
	}
	defer rows.Close()

	for rows.Next() {
		var reviewerID, username, displayName string
		var maxReviews, active, pending int

		if err := rows.Scan(&reviewerID, &username, &displayName, &maxReviews, &active, &pending); err != nil {
			continue
		}

		total := active + pending
		var capacityScore float64
		if maxReviews > 0 {
			remaining := maxReviews - total
			if remaining <= 0 {
				capacityScore = 0.0
			} else {
				capacityScore = float64(remaining) / float64(maxReviews)
			}
		}

		key := fmt.Sprintf("reviewer:capacity:%s", reviewerID)
		s.rdb.HSet(ctx, key,
			"reviewer_id", reviewerID,
			"username", username,
			"display_name", displayName,
			"active_reviews", strconv.Itoa(active),
			"pending_reviews", strconv.Itoa(pending),
			"max_reviews", strconv.Itoa(maxReviews),
			"capacity_score", fmt.Sprintf("%.4f", capacityScore),
			"updated_at", time.Now().Format(time.RFC3339),
		)
		s.rdb.Expire(ctx, key, 10*time.Minute)

		// Store snapshot for time-series
		s.db.Exec(ctx, `
			INSERT INTO capacity_snapshots (reviewer_id, active_reviews, pending_reviews, capacity_score)
			VALUES ($1, $2, $3, $4)`,
			reviewerID, active, pending, capacityScore,
		)
	}
}

func (s *Server) subscribeReviewEvents() {
	time.Sleep(3 * time.Second)

	// Subscribe to assignment events to update capacity immediately
	s.nc.Subscribe("pr.assigned.notify", func(msg *nats.Msg) {
		var data map[string]interface{}
		if err := json.Unmarshal(msg.Data, &data); err != nil {
			return
		}

		// Trigger immediate capacity sync
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		s.syncAllCapacity(ctx)
	})

	log.Println("Capacity tracker subscribed to assignment events")
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "capacity"})
}

func (s *Server) handleGetCapacity(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	rows, err := s.db.Query(ctx, `
		SELECT 
			r.id, r.username, r.display_name, r.max_concurrent_reviews,
			COUNT(ra.id) FILTER (WHERE ra.status = 'in_progress') as active,
			COUNT(ra.id) FILTER (WHERE ra.status = 'pending') as pending
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		WHERE r.is_active = true
		GROUP BY r.id, r.username, r.display_name, r.max_concurrent_reviews
		ORDER BY r.display_name`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var statuses []ReviewerStatus
	for rows.Next() {
		var s ReviewerStatus
		var active, pending int
		if err := rows.Scan(&s.ReviewerID, &s.Username, &s.DisplayName,
			&s.MaxReviews, &active, &pending); err != nil {
			continue
		}
		s.ActiveReviews = active
		s.PendingReviews = pending
		total := active + pending
		if s.MaxReviews > 0 {
			remaining := s.MaxReviews - total
			if remaining <= 0 {
				s.CapacityScore = 0.0
			} else {
				s.CapacityScore = float64(remaining) / float64(s.MaxReviews)
			}
		}
		s.IsAvailable = s.CapacityScore > 0
		s.UpdatedAt = time.Now()
		statuses = append(statuses, s)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(statuses)
}

func (s *Server) handleGetReviewerCapacity(w http.ResponseWriter, r *http.Request) {
	reviewerID := chi.URLParam(r, "reviewer_id")
	ctx := r.Context()

	// Try Redis first
	key := fmt.Sprintf("reviewer:capacity:%s", reviewerID)
	vals, err := s.rdb.HGetAll(ctx, key).Result()
	if err == nil && len(vals) > 0 {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(vals)
		return
	}

	// Fallback to DB
	var status ReviewerStatus
	var active, pending int
	err = s.db.QueryRow(ctx, `
		SELECT 
			r.id, r.username, r.display_name, r.max_concurrent_reviews,
			COUNT(ra.id) FILTER (WHERE ra.status = 'in_progress') as active,
			COUNT(ra.id) FILTER (WHERE ra.status = 'pending') as pending
		FROM reviewers r
		LEFT JOIN review_assignments ra ON ra.reviewer_id = r.id
		WHERE r.id = $1
		GROUP BY r.id, r.username, r.display_name, r.max_concurrent_reviews`,
		reviewerID).Scan(&status.ReviewerID, &status.Username, &status.DisplayName,
		&status.MaxReviews, &active, &pending)
	if err != nil {
		http.Error(w, "reviewer not found", http.StatusNotFound)
		return
	}

	status.ActiveReviews = active
	status.PendingReviews = pending
	total := active + pending
	if status.MaxReviews > 0 {
		remaining := status.MaxReviews - total
		if remaining <= 0 {
			status.CapacityScore = 0.0
		} else {
			status.CapacityScore = float64(remaining) / float64(status.MaxReviews)
		}
	}
	status.IsAvailable = status.CapacityScore > 0
	status.UpdatedAt = time.Now()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func (s *Server) handleStartReview(w http.ResponseWriter, r *http.Request) {
	assignmentID := chi.URLParam(r, "assignment_id")
	ctx := r.Context()

	_, err := s.db.Exec(ctx, `
		UPDATE review_assignments 
		SET status = 'in_progress', pickup_at = NOW()
		WHERE id = $1`, assignmentID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	s.syncAllCapacity(ctx)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "started"})
}

func (s *Server) handleCompleteReview(w http.ResponseWriter, r *http.Request) {
	assignmentID := chi.URLParam(r, "assignment_id")
	ctx := r.Context()

	var reviewerID, prID string
	err := s.db.QueryRow(ctx, `
		UPDATE review_assignments 
		SET status = 'completed', completed_at = NOW()
		WHERE id = $1
		RETURNING reviewer_id, pr_id`, assignmentID).
		Scan(&reviewerID, &prID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Update PR state
	s.db.Exec(ctx, `UPDATE pull_requests SET state = 'in_review', updated_at = NOW() WHERE id = $1`, prID)

	// Update Redis capacity
	key := fmt.Sprintf("reviewer:capacity:%s", reviewerID)
	s.rdb.HIncrBy(ctx, key, "active_reviews", -1)

	s.syncAllCapacity(ctx)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "completed"})
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

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}