package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

type Reviewer struct {
	ID                  string   `json:"id"`
	Username            string   `json:"username"`
	DisplayName         string   `json:"display_name"`
	Email               string   `json:"email"`
	SlackUserID         string   `json:"slack_user_id"`
	Timezone            string   `json:"timezone"`
	MaxConcurrentReviews int     `json:"max_concurrent_reviews"`
	IsActive            bool     `json:"is_active"`
}

type ReviewerExpertise struct {
	ReviewerID     string  `json:"reviewer_id"`
	FilePattern    string  `json:"file_pattern"`
	ExpertiseLevel int     `json:"expertise_level"`
	PRCount        int     `json:"pr_count"`
}

type ReviewerCapacity struct {
	ReviewerID      string  `json:"reviewer_id"`
	ActiveReviews   int     `json:"active_reviews"`
	CapacityScore   float64 `json:"capacity_score"`
}

type RoutingCandidate struct {
	Reviewer       Reviewer
	CapacityScore  float64
	ExpertiseScore float64
	FinalScore     float64
	Reason         string
}

type AnalyzedPREvent struct {
	PRID                     string             `json:"pr_id"`
	ComplexityScore          float64            `json:"complexity_score"`
	RiskScore                float64            `json:"risk_score"`
	EstimatedReviewMinutes   int                `json:"estimated_review_minutes"`
	RecommendedReviewersCount int               `json:"recommended_reviewers_count"`
	Factors                  map[string]float64 `json:"factors"`
}

type AssignmentResult struct {
	PRID        string `json:"pr_id"`
	Assignments []struct {
		ReviewerID   string  `json:"reviewer_id"`
		ReviewerName string  `json:"reviewer_name"`
		Score        float64 `json:"score"`
		Reason       string  `json:"reason"`
	} `json:"assignments"`
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

	// Subscribe to analyzed PR events
	go srv.subscribeAnalyzedPRs()

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", srv.handleHealth)
	r.Post("/route/{pr_id}", srv.handleManualRoute)
	r.Get("/assignments", srv.handleGetAssignments)
	r.Get("/queue", srv.handleGetQueue)

	log.Println("Routing service starting on :8082")
	if err := http.ListenAndServe(":8082", r); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func (s *Server) subscribeAnalyzedPRs() {
	time.Sleep(3 * time.Second) // Wait for NATS streams to be ready

	_, err := s.js.Subscribe(
		"pr.analyzed.ready",
		func(msg *nats.Msg) {
			var event AnalyzedPREvent
			if err := json.Unmarshal(msg.Data, &event); err != nil {
				log.Printf("Failed to parse analyzed PR event: %v", err)
				msg.Nak()
				return
			}

			log.Printf("Routing PR %s (complexity=%.1f, risk=%.1f)",
				event.PRID, event.ComplexityScore, event.RiskScore)

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()

			if err := s.routePR(ctx, event); err != nil {
				log.Printf("Failed to route PR %s: %v", event.PRID, err)
				msg.Nak()
				return
			}

			msg.Ack()
		},
		nats.Durable("routing-worker"),
		nats.ManualAck(),
	)
	if err != nil {
		log.Printf("Failed to subscribe to pr.analyzed.ready: %v", err)
	} else {
		log.Println("Subscribed to pr.analyzed.ready")
	}
}

func (s *Server) routePR(ctx context.Context, event AnalyzedPREvent) error {
	// Get PR details
	var pr struct {
		ID           string
		Title        string
		Author       string
		RepoFullName string
		Priority     int
		Labels       []string
	}

	err := s.db.QueryRow(ctx, `
		SELECT id, title, author_username, repo_full_name, priority, COALESCE(labels, '{}')
		FROM pull_requests WHERE id = $1`, event.PRID).
		Scan(&pr.ID, &pr.Title, &pr.Author, &pr.RepoFullName, &pr.Priority, &pr.Labels)
	if err != nil {
		return fmt.Errorf("get PR: %w", err)
	}

	// Get available reviewers (not the author)
	reviewers, err := s.getAvailableReviewers(ctx, pr.Author)
	if err != nil {
		return fmt.Errorf("get reviewers: %w", err)
	}

	if len(reviewers) == 0 {
		log.Printf("No available reviewers for PR %s", event.PRID)
		return nil
	}

	// Score each reviewer
	candidates := s.scoreReviewers(ctx, reviewers, event, pr.RepoFullName)

	// Sort by final score descending
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].FinalScore > candidates[j].FinalScore
	})

	// Assign top N reviewers
	numToAssign := event.RecommendedReviewersCount
	if numToAssign > len(candidates) {
		numToAssign = len(candidates)
	}
	if numToAssign == 0 {
		numToAssign = 1
	}

	assigned := candidates[:numToAssign]

	// Persist assignments
	for _, candidate := range assigned {
		assignmentID := uuid.New().String()
		_, err := s.db.Exec(ctx, `
			INSERT INTO review_assignments (id, pr_id, reviewer_id, assigned_at, status, routing_reason, score)
			VALUES ($1, $2, $3, NOW(), 'pending', $4, $5)
			ON CONFLICT DO NOTHING`,
			assignmentID, event.PRID, candidate.Reviewer.ID,
			candidate.Reason, candidate.FinalScore,
		)
		if err != nil {
			log.Printf("Warning: failed to insert assignment: %v", err)
		}

		// Update reviewer capacity in Redis
		key := fmt.Sprintf("reviewer:capacity:%s", candidate.Reviewer.ID)
		s.rdb.HIncrBy(ctx, key, "active_reviews", 1)
		s.rdb.Expire(ctx, key, 24*time.Hour)

		log.Printf("Assigned PR %s to %s (score=%.2f, reason=%s)",
			event.PRID, candidate.Reviewer.Username, candidate.FinalScore, candidate.Reason)
	}

	// Update PR state
	s.db.Exec(ctx, `UPDATE pull_requests SET state = 'assigned', updated_at = NOW() WHERE id = $1`, event.PRID)

	// Remove from priority queue
	s.rdb.ZRem(ctx, "pr:queue:priority", event.PRID)
	s.rdb.Set(ctx, fmt.Sprintf("pr:queue:%s", event.PRID), "assigned", 24*time.Hour)

	// Publish assignment event for notification service
	assignmentNotif := map[string]interface{}{
		"pr_id":           event.PRID,
		"pr_title":        pr.Title,
		"pr_repo":         pr.RepoFullName,
		"pr_author":       pr.Author,
		"complexity_score": event.ComplexityScore,
		"risk_score":      event.RiskScore,
		"estimated_minutes": event.EstimatedReviewMinutes,
		"assignees":       buildAssigneeList(assigned),
	}

	notifBytes, _ := json.Marshal(assignmentNotif)
	s.js.Publish("pr.assigned.notify", notifBytes)

	return nil
}

func buildAssigneeList(candidates []RoutingCandidate) []map[string]interface{} {
	result := make([]map[string]interface{}, len(candidates))
	for i, c := range candidates {
		result[i] = map[string]interface{}{
			"reviewer_id":   c.Reviewer.ID,
			"reviewer_name": c.Reviewer.DisplayName,
			"username":      c.Reviewer.Username,
			"slack_user_id": c.Reviewer.SlackUserID,
			"score":         c.FinalScore,
			"reason":        c.Reason,
		}
	}
	return result
}

func (s *Server) getAvailableReviewers(ctx context.Context, excludeAuthor string) ([]Reviewer, error) {
	rows, err := s.db.Query(ctx, `
		SELECT id, username, display_name, email, slack_user_id, timezone, max_concurrent_reviews
		FROM reviewers
		WHERE is_active = true AND username != $1
		ORDER BY username`, excludeAuthor)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var reviewers []Reviewer
	for rows.Next() {
		var r Reviewer
		r.IsActive = true
		err := rows.Scan(&r.ID, &r.Username, &r.DisplayName, &r.Email,
			&r.SlackUserID, &r.Timezone, &r.MaxConcurrentReviews)
		if err != nil {
			continue
		}
		reviewers = append(reviewers, r)
	}
	return reviewers, rows.Err()
}

func (s *Server) scoreReviewers(ctx context.Context, reviewers []Reviewer,
	event AnalyzedPREvent, repo string) []RoutingCandidate {

	candidates := make([]RoutingCandidate, 0, len(reviewers))

	for _, reviewer := range reviewers {
		// Get capacity from Redis
		capacityScore := s.getCapacityScore(ctx, reviewer)

		// Skip if fully booked
		if capacityScore <= 0 {
			continue
		}

		// Get expertise score
		expertiseScore := s.getExpertiseScore(ctx, reviewer.ID, repo)

		// Build routing reason
		var reasons []string
		if capacityScore > 0.7 {
			reasons = append(reasons, "high availability")
		} else if capacityScore > 0.3 {
			reasons = append(reasons, "moderate availability")
		}

		if expertiseScore > 7 {
			reasons = append(reasons, fmt.Sprintf("expertise match (%.0f/10)", expertiseScore))
		}

		// Prefer expert for risky PRs
		var weightCapacity, weightExpertise float64
		if event.RiskScore > 7.0 {
			// High risk: prioritize expertise
			weightCapacity = 0.3
			weightExpertise = 0.7
			reasons = append(reasons, "high-risk PR needs expert")
		} else if event.ComplexityScore > 7.0 {
			// Complex: balance
			weightCapacity = 0.4
			weightExpertise = 0.6
		} else {
			// Normal: prioritize availability
			weightCapacity = 0.6
			weightExpertise = 0.4
		}

		finalScore := capacityScore*weightCapacity + expertiseScore/10.0*weightExpertise

		reason := "load balanced"
		if len(reasons) > 0 {
			reason = strings.Join(reasons, ", ")
		}

		candidates = append(candidates, RoutingCandidate{
			Reviewer:       reviewer,
			CapacityScore:  capacityScore,
			ExpertiseScore: expertiseScore,
			FinalScore:     finalScore,
			Reason:         reason,
		})
	}

	return candidates
}

func (s *Server) getCapacityScore(ctx context.Context, reviewer Reviewer) float64 {
	key := fmt.Sprintf("reviewer:capacity:%s", reviewer.ID)
	vals, err := s.rdb.HGetAll(ctx, key).Result()
	if err != nil || len(vals) == 0 {
		// No data in Redis, assume fully available
		return 1.0
	}

	// Count active reviews from DB as fallback
	var activeCount int
	s.db.QueryRow(ctx, `
		SELECT COUNT(*) FROM review_assignments
		WHERE reviewer_id = $1 AND status IN ('pending', 'in_progress')`,
		reviewer.ID).Scan(&activeCount)

	if activeCount >= reviewer.MaxConcurrentReviews {
		return 0.0
	}

	remaining := reviewer.MaxConcurrentReviews - activeCount
	return float64(remaining) / float64(reviewer.MaxConcurrentReviews)
}

func (s *Server) getExpertiseScore(ctx context.Context, reviewerID, repo string) float64 {
	// Lookup expertise for this repo/file pattern
	rows, err := s.db.Query(ctx, `
		SELECT file_pattern, expertise_level, pr_count
		FROM reviewer_expertise
		WHERE reviewer_id = $1
		ORDER BY expertise_level DESC`, reviewerID)
	if err != nil {
		return 5.0 // Default
	}
	defer rows.Close()

	var maxExpertise float64 = 5.0
	repoLower := strings.ToLower(repo)

	for rows.Next() {
		var pattern string
		var level, prCount int
		if err := rows.Scan(&pattern, &level, &prCount); err != nil {
			continue
		}

		// Simple pattern matching against repo name
		patternLower := strings.ToLower(strings.TrimPrefix(pattern, "*."))
		if strings.Contains(repoLower, patternLower) {
			score := float64(level)
			// Boost score based on experience
			if prCount > 100 {
				score = min(10.0, score+1.0)
			}
			if score > maxExpertise {
				maxExpertise = score
			}
		}
	}

	return maxExpertise
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "routing"})
}

func (s *Server) handleManualRoute(w http.ResponseWriter, r *http.Request) {
	prID := chi.URLParam(r, "pr_id")
	ctx := r.Context()

	// Get PR analysis from Redis/DB
	var complexityScore, riskScore float64
	var estMinutes int

	vals, err := s.rdb.HGetAll(ctx, fmt.Sprintf("pr:analysis:%s", prID)).Result()
	if err == nil && len(vals) > 0 {
		fmt.Sscanf(vals["complexity_score"], "%f", &complexityScore)
		fmt.Sscanf(vals["risk_score"], "%f", &riskScore)
		fmt.Sscanf(vals["estimated_review_minutes"], "%d", &estMinutes)
	} else {
		s.db.QueryRow(ctx, `
			SELECT COALESCE(complexity_score, 5.0), COALESCE(risk_score, 5.0), COALESCE(estimated_review_minutes, 60)
			FROM pull_requests WHERE id = $1`, prID).
			Scan(&complexityScore, &riskScore, &estMinutes)
	}

	event := AnalyzedPREvent{
		PRID:                      prID,
		ComplexityScore:           complexityScore,
		RiskScore:                 riskScore,
		EstimatedReviewMinutes:    estMinutes,
		RecommendedReviewersCount: 1,
	}
	if complexityScore > 7 || riskScore > 7 {
		event.RecommendedReviewersCount = 2
	}

	if err := s.routePR(ctx, event); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "routed", "pr_id": prID})
}

func (s *Server) handleGetAssignments(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := s.db.Query(ctx, `
		SELECT 
			ra.id, ra.pr_id, ra.reviewer_id, ra.assigned_at, ra.status,
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

	type Assignment struct {
		ID              string    `json:"id"`
		PRID            string    `json:"pr_id"`
		ReviewerID      string    `json:"reviewer_id"`
		AssignedAt      time.Time `json:"assigned_at"`
		Status          string    `json:"status"`
		RoutingReason   string    `json:"routing_reason"`
		Score           float64   `json:"score"`
		PRTitle         string    `json:"pr_title"`
		PRRepo          string    `json:"pr_repo"`
		ComplexityScore *float64  `json:"complexity_score"`
		RiskScore       *float64  `json:"risk_score"`
		ReviewerUsername string   `json:"reviewer_username"`
		ReviewerName    string    `json:"reviewer_name"`
	}

	var assignments []Assignment
	for rows.Next() {
		var a Assignment
		err := rows.Scan(
			&a.ID, &a.PRID, &a.ReviewerID, &a.AssignedAt, &a.Status,
			&a.RoutingReason, &a.Score,
			&a.PRTitle, &a.PRRepo, &a.ComplexityScore, &a.RiskScore,
			&a.ReviewerUsername, &a.ReviewerName,
		)
		if err != nil {
			log.Printf("scan error: %v", err)
			continue
		}
		assignments = append(assignments, a)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(assignments)
}

func (s *Server) handleGetQueue(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := s.db.Query(ctx, `
		SELECT id, external_id, repo_full_name, title, author_username, 
		       state, lines_added, lines_deleted, files_changed,
		       complexity_score, risk_score, priority, created_at
		FROM pull_requests
		WHERE state IN ('open', 'assigned')
		ORDER BY priority DESC, created_at ASC
		LIMIT 50`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type QueueItem struct {
		ID              string    `json:"id"`
		ExternalID      string    `json:"external_id"`
		Repo            string    `json:"repo"`
		Title           string    `json:"title"`
		Author          string    `json:"author"`
		State           string    `json:"state"`
		LinesAdded      int       `json:"lines_added"`
		LinesDeleted    int       `json:"lines_deleted"`
		FilesChanged    int       `json:"files_changed"`
		ComplexityScore *float64  `json:"complexity_score"`
		RiskScore       *float64  `json:"risk_score"`
		Priority        int       `json:"priority"`
		CreatedAt       time.Time `json:"created_at"`
	}

	var items []QueueItem
	for rows.Next() {
		var item QueueItem
		err := rows.Scan(
			&item.ID, &item.ExternalID, &item.Repo, &item.Title,
			&item.Author, &item.State, &item.LinesAdded, &item.LinesDeleted,
			&item.FilesChanged, &item.ComplexityScore, &item.RiskScore,
			&item.Priority, &item.CreatedAt,
		)
		if err != nil {
			pgx.ErrNoRows.Error()
			continue
		}
		items = append(items, item)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(items)
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

func min(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}