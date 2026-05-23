package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/code-review-coordinator/internal/config"
	"github.com/code-review-coordinator/internal/models"
	"github.com/code-review-coordinator/internal/store"
)

type CapacityService struct {
	cfg    *config.Config
	pg     *store.PostgresStore
	redis  *store.RedisStore
	logger *log.Logger
}

func main() {
	logger := log.New(os.Stdout, "[capacity] ", log.LstdFlags|log.Lshortfile)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("Failed to load config: %v", err)
	}

	pg, err := store.NewPostgresStore(cfg.PostgresConnectionString())
	if err != nil {
		logger.Fatalf("Failed to connect to PostgreSQL: %v", err)
	}
	defer pg.Close()

	redis, err := store.NewRedisStore(cfg.RedisAddress())
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redis.Close()

	svc := &CapacityService{
		cfg:    cfg,
		pg:     pg,
		redis:  redis,
		logger: logger,
	}

	// Sync capacity to Redis on startup
	if err := svc.syncCapacityToRedis(context.Background()); err != nil {
		logger.Printf("Warning: initial capacity sync failed: %v", err)
	}

	// Background capacity polling
	go svc.capacityPollingLoop(context.Background())

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", svc.healthHandler)

	// Reviewer management
	r.Post("/reviewers", svc.createReviewerHandler)
	r.Get("/reviewers", svc.listReviewersHandler)
	r.Get("/reviewers/{username}", svc.getReviewerHandler)
	r.Put("/reviewers/{username}/availability", svc.updateAvailabilityHandler)
	r.Put("/reviewers/{username}/load", svc.updateLoadHandler)
	r.Post("/reviewers/{username}/expertise", svc.addExpertiseHandler)

	// Events (from webhook)
	r.Post("/events/review-completed", svc.reviewCompletedHandler)
	r.Post("/events/review-started", svc.reviewStartedHandler)

	// Stats
	r.Get("/stats", svc.getStatsHandler)

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.CapacityServicePort),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		logger.Printf("Capacity service starting on port %d", cfg.CapacityServicePort)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatalf("Server failed: %v", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	srv.Shutdown(ctx)
	logger.Println("Capacity service stopped")
}

func (s *CapacityService) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "capacity"})
}

func (s *CapacityService) createReviewerHandler(w http.ResponseWriter, r *http.Request) {
	var reviewer models.Reviewer
	if err := json.NewDecoder(r.Body).Decode(&reviewer); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if reviewer.Username == "" {
		http.Error(w, "username is required", http.StatusBadRequest)
		return
	}
	if reviewer.MaxLoad == 0 {
		reviewer.MaxLoad = 3
	}
	reviewer.IsAvailable = true

	if err := s.pg.UpsertReviewer(&reviewer); err != nil {
		s.logger.Printf("Failed to create reviewer: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Sync to Redis
	ctx := r.Context()
	s.redis.SetReviewerCapacity(ctx, reviewer.Username, reviewer.CurrentLoad, reviewer.MaxLoad)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(reviewer)
}

func (s *CapacityService) listReviewersHandler(w http.ResponseWriter, r *http.Request) {
	reviewers, err := s.pg.ListReviewers()
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Enrich with Redis real-time data
	ctx := r.Context()
	for _, rev := range reviewers {
		load, maxLoad, err := s.redis.GetReviewerCapacity(ctx, rev.Username)
		if err == nil && maxLoad > 0 {
			rev.CurrentLoad = load
			rev.MaxLoad = maxLoad
		}
	}

	w.Header().Set("Content-Type", "application/json")
	if reviewers == nil {
		reviewers = []*models.Reviewer{}
	}
	json.NewEncoder(w).Encode(reviewers)
}

func (s *CapacityService) getReviewerHandler(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")
	reviewer, err := s.pg.GetReviewer(username)
	if err != nil {
		http.Error(w, "Reviewer not found", http.StatusNotFound)
		return
	}

	// Enrich with Redis data
	ctx := r.Context()
	load, maxLoad, err := s.redis.GetReviewerCapacity(ctx, username)
	if err == nil && maxLoad > 0 {
		reviewer.CurrentLoad = load
		reviewer.MaxLoad = maxLoad
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(reviewer)
}

func (s *CapacityService) updateAvailabilityHandler(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")

	var req struct {
		IsAvailable bool `json:"is_available"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	_, err := s.pg.GetReviewer(username)
	if err != nil {
		http.Error(w, "Reviewer not found", http.StatusNotFound)
		return
	}

	reviewer := &models.Reviewer{
		Username:    username,
		IsAvailable: req.IsAvailable,
	}
	if err := s.pg.UpsertReviewer(reviewer); err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"username":     username,
		"is_available": req.IsAvailable,
	})
}

func (s *CapacityService) updateLoadHandler(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")

	var req struct {
		Delta int `json:"delta"` // +1 or -1
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	ctx := r.Context()
	if req.Delta > 0 {
		s.pg.IncrementReviewerLoad(username)
		s.redis.IncrementReviewerLoad(ctx, username)
	} else if req.Delta < 0 {
		s.pg.DecrementReviewerLoad(username)
		s.redis.DecrementReviewerLoad(ctx, username)
	}

	reviewer, _ := s.pg.GetReviewer(username)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(reviewer)
}

func (s *CapacityService) addExpertiseHandler(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")

	var req struct {
		FilePattern    string  `json:"file_pattern"`
		ExpertiseScore float64 `json:"expertise_score"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if req.FilePattern == "" {
		http.Error(w, "file_pattern is required", http.StatusBadRequest)
		return
	}
	if req.ExpertiseScore == 0 {
		req.ExpertiseScore = 0.7
	}

	if err := s.pg.UpsertExpertise(username, req.FilePattern, req.ExpertiseScore); err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"username":        username,
		"file_pattern":    req.FilePattern,
		"expertise_score": req.ExpertiseScore,
	})
}

func (s *CapacityService) reviewCompletedHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		PRID     int64  `json:"pr_id"`
		Reviewer string `json:"reviewer"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	ctx := r.Context()

	// Decrement reviewer load
	s.pg.DecrementReviewerLoad(req.Reviewer)
	s.redis.DecrementReviewerLoad(ctx, req.Reviewer)

	// Update PR status
	s.pg.UpdatePRStatus(req.PRID, "completed")

	// Log event
	s.pg.LogEvent(req.PRID, req.Reviewer, "review_completed", "Review marked as completed")

	s.logger.Printf("Review completed: PR %d by %s", req.PRID, req.Reviewer)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
}

func (s *CapacityService) reviewStartedHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		PRID     int64  `json:"pr_id"`
		Reviewer string `json:"reviewer"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	// Update PR status to in_review
	s.pg.UpdatePRStatus(req.PRID, "in_review")
	s.pg.LogEvent(req.PRID, req.Reviewer, "review_started", "Review started")

	s.logger.Printf("Review started: PR %d by %s", req.PRID, req.Reviewer)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
}

func (s *CapacityService) getStatsHandler(w http.ResponseWriter, r *http.Request) {
	stats, err := s.pg.GetReviewerStats()
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if stats == nil {
		stats = []models.ReviewerStats{}
	}
	json.NewEncoder(w).Encode(stats)
}

// syncCapacityToRedis syncs PostgreSQL reviewer state to Redis
func (s *CapacityService) syncCapacityToRedis(ctx context.Context) error {
	reviewers, err := s.pg.ListReviewers()
	if err != nil {
		return err
	}

	for _, r := range reviewers {
		if err := s.redis.SetReviewerCapacity(ctx, r.Username, r.CurrentLoad, r.MaxLoad); err != nil {
			s.logger.Printf("Failed to sync reviewer %s to Redis: %v", r.Username, err)
		}
	}

	s.logger.Printf("Synced %d reviewers to Redis", len(reviewers))
	return nil
}

// capacityPollingLoop periodically re-syncs state
func (s *CapacityService) capacityPollingLoop(ctx context.Context) {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := s.syncCapacityToRedis(ctx); err != nil {
				s.logger.Printf("Capacity sync error: %v", err)
			}
		}
	}
}