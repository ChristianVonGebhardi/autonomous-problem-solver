package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
	"context"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/code-review-coordinator/internal/config"
	"github.com/code-review-coordinator/internal/models"
	"github.com/code-review-coordinator/internal/store"
)

type DashboardAPI struct {
	cfg    *config.Config
	pg     *store.PostgresStore
	redis  *store.RedisStore
	logger *log.Logger
}

func main() {
	logger := log.New(os.Stdout, "[dashboard] ", log.LstdFlags|log.Lshortfile)

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

	api := &DashboardAPI{
		cfg:    cfg,
		pg:     pg,
		redis:  redis,
		logger: logger,
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestID)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type"},
		AllowCredentials: false,
		MaxAge:           300,
	}))

	// API routes
	r.Get("/health", api.healthHandler)
	r.Route("/api", func(r chi.Router) {
		r.Get("/metrics", api.metricsHandler)
		r.Get("/reviewers", api.reviewersHandler)
		r.Get("/reviewers/stats", api.reviewerStatsHandler)
		r.Get("/prs", api.prsHandler)
		r.Get("/prs/queue", api.queueHandler)
		r.Get("/prs/{id}", api.getPRHandler)
		r.Post("/prs/{id}/reassign", api.reassignPRHandler)
		r.Get("/events", api.eventsHandler)
	})

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.DashboardAPIPort),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		logger.Printf("Dashboard API starting on port %d", cfg.DashboardAPIPort)
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
	logger.Println("Dashboard API stopped")
}

func (a *DashboardAPI) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "dashboard"})
}

func (a *DashboardAPI) metricsHandler(w http.ResponseWriter, r *http.Request) {
	metrics, err := a.pg.GetMetricsOverview()
	if err != nil {
		a.logger.Printf("Failed to get metrics: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Enrich with Redis queue info
	ctx := r.Context()
	queueLen, _ := a.redis.GetQueueLength(ctx)

	response := map[string]interface{}{
		"metrics":      metrics,
		"queue_length": queueLen,
		"timestamp":    time.Now().UTC(),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func (a *DashboardAPI) reviewersHandler(w http.ResponseWriter, r *http.Request) {
	reviewers, err := a.pg.ListReviewers()
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Enrich with Redis real-time capacity
	ctx := r.Context()
	for _, rev := range reviewers {
		load, maxLoad, err := a.redis.GetReviewerCapacity(ctx, rev.Username)
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

func (a *DashboardAPI) reviewerStatsHandler(w http.ResponseWriter, r *http.Request) {
	stats, err := a.pg.GetReviewerStats()
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

func (a *DashboardAPI) prsHandler(w http.ResponseWriter, r *http.Request) {
	status := r.URL.Query().Get("status")
	prs, err := a.pg.ListPRs(status, 100)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if prs == nil {
		prs = []*models.PullRequest{}
	}
	json.NewEncoder(w).Encode(prs)
}

func (a *DashboardAPI) queueHandler(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	prIDs, err := a.redis.GetQueuedPRs(ctx)
	if err != nil {
		http.Error(w, "Redis error", http.StatusInternalServerError)
		return
	}

	// Fetch PR details for queued items
	var queuedPRs []*models.PullRequest
	for _, id := range prIDs {
		pr, err := a.pg.GetPR(id)
		if err == nil {
			queuedPRs = append(queuedPRs, pr)
		}
	}

	if queuedPRs == nil {
		queuedPRs = []*models.PullRequest{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"queue_length": len(queuedPRs),
		"prs":          queuedPRs,
	})
}

func (a *DashboardAPI) getPRHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	var id int64
	fmt.Sscanf(idStr, "%d", &id)

	pr, err := a.pg.GetPR(id)
	if err != nil {
		http.Error(w, "PR not found", http.StatusNotFound)
		return
	}

	// Get PR files
	files, _ := a.pg.GetPRFiles(id)
	if files == nil {
		files = []models.PRFile{}
	}

	// Get PR events
	events, _ := a.pg.GetPREvents(id)
	if events == nil {
		events = []models.ReviewEvent{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"pr":     pr,
		"files":  files,
		"events": events,
	})
}

func (a *DashboardAPI) reassignPRHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	var id int64
	fmt.Sscanf(idStr, "%d", &id)

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

	// Get current PR
	pr, err := a.pg.GetPR(id)
	if err != nil {
		http.Error(w, "PR not found", http.StatusNotFound)
		return
	}

	// Decrement old reviewer load
	if pr.AssignedReviewer != "" && pr.AssignedReviewer != req.Reviewer {
		a.pg.DecrementReviewerLoad(pr.AssignedReviewer)
		ctx := r.Context()
		a.redis.DecrementReviewerLoad(ctx, pr.AssignedReviewer)
	}

	// Assign new reviewer
	if err := a.pg.AssignReviewer(id, req.Reviewer); err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Increment new reviewer load
	a.pg.IncrementReviewerLoad(req.Reviewer)
	ctx := r.Context()
	a.redis.IncrementReviewerLoad(ctx, req.Reviewer)

	reason := req.Reason
	if reason == "" {
		reason = "Manual reassignment via dashboard"
	}
	a.pg.LogEvent(id, req.Reviewer, "reassigned", reason)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":   "reassigned",
		"reviewer": req.Reviewer,
	})
}

func (a *DashboardAPI) eventsHandler(w http.ResponseWriter, r *http.Request) {
	events, err := a.pg.GetRecentEvents(50)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if events == nil {
		events = []models.ReviewEvent{}
	}
	json.NewEncoder(w).Encode(events)
}