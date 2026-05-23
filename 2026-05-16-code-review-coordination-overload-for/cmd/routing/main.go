package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/code-review-coordinator/internal/config"
	"github.com/code-review-coordinator/internal/models"
	"github.com/code-review-coordinator/internal/store"
)

type RoutingService struct {
	cfg    *config.Config
	pg     *store.PostgresStore
	redis  *store.RedisStore
	logger *log.Logger
}

func main() {
	logger := log.New(os.Stdout, "[routing] ", log.LstdFlags|log.Lshortfile)

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

	svc := &RoutingService{
		cfg:    cfg,
		pg:     pg,
		redis:  redis,
		logger: logger,
	}

	// Background routing loop
	go svc.routingLoop(context.Background())

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", svc.healthHandler)
	r.Post("/route", svc.routePRHandler)
	r.Post("/route/{prID}", svc.routeSpecificPRHandler)
	r.Get("/queue", svc.getQueueHandler)

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.RoutingServicePort),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		logger.Printf("Routing service starting on port %d", cfg.RoutingServicePort)
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
	logger.Println("Routing service stopped")
}

func (s *RoutingService) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "routing"})
}

func (s *RoutingService) getQueueHandler(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	queueLen, _ := s.redis.GetQueueLength(ctx)
	prIDs, _ := s.redis.GetQueuedPRs(ctx)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"queue_length": queueLen,
		"pr_ids":       prIDs,
	})
}

func (s *RoutingService) routePRHandler(w http.ResponseWriter, r *http.Request) {
	var req models.RoutingRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	ctx := r.Context()
	result, err := s.routePR(ctx, req.PRID, req.Files)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (s *RoutingService) routeSpecificPRHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "prID")
	var prID int64
	fmt.Sscanf(idStr, "%d", &prID)

	ctx := r.Context()
	pr, err := s.pg.GetPR(prID)
	if err != nil {
		http.Error(w, "PR not found", http.StatusNotFound)
		return
	}

	files, _ := s.pg.GetPRFiles(prID)
	fileNames := make([]string, len(files))
	for i, f := range files {
		fileNames[i] = f.Filename
	}

	result, err := s.routePR(ctx, pr.ID, fileNames)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

// routePR assigns the best available reviewer to a PR
func (s *RoutingService) routePR(ctx context.Context, prID int64, files []string) (*models.RoutingResponse, error) {
	// Acquire routing lock to prevent double-assignment
	locked, err := s.redis.AcquireRoutingLock(ctx, prID, 30*time.Second)
	if err != nil {
		return nil, fmt.Errorf("failed to acquire lock: %w", err)
	}
	if !locked {
		return nil, fmt.Errorf("PR %d is already being routed", prID)
	}
	defer s.redis.ReleaseRoutingLock(ctx, prID)

	pr, err := s.pg.GetPR(prID)
	if err != nil {
		return nil, fmt.Errorf("PR not found: %w", err)
	}

	// Don't re-assign already assigned PRs
	if pr.Status == "assigned" || pr.Status == "in_review" || pr.Status == "completed" {
		return &models.RoutingResponse{
			AssignedReviewer: pr.AssignedReviewer,
			Confidence:       1.0,
			Reason:           "already assigned",
		}, nil
	}

	reviewers, err := s.pg.GetAvailableReviewers()
	if err != nil {
		return nil, fmt.Errorf("failed to get reviewers: %w", err)
	}

	if len(reviewers) == 0 {
		return nil, fmt.Errorf("no available reviewers")
	}

	// Score each reviewer
	best, score, reason := s.selectBestReviewer(pr, reviewers, files)

	// Assign in database
	if err := s.pg.AssignReviewer(prID, best.Username); err != nil {
		return nil, fmt.Errorf("failed to assign reviewer: %w", err)
	}

	// Update load
	if err := s.pg.IncrementReviewerLoad(best.Username); err != nil {
		s.logger.Printf("Warning: failed to increment load for %s: %v", best.Username, err)
	}

	// Update Redis cache
	newLoad := best.CurrentLoad + 1
	s.redis.SetReviewerCapacity(ctx, best.Username, newLoad, best.MaxLoad)

	// Remove from queue
	s.redis.RemoveFromQueue(ctx, prID)

	// Cache updated PR
	pr.AssignedReviewer = best.Username
	pr.Status = "assigned"
	s.redis.CachePR(ctx, pr, 1*time.Hour)

	// Log event
	s.pg.LogEvent(prID, best.Username, "assigned", fmt.Sprintf("Routing score: %.2f. %s", score, reason))

	s.logger.Printf("PR %d assigned to %s (score: %.2f, reason: %s)", prID, best.Username, score, reason)

	// Trigger notification
	go s.triggerNotification(pr, best)

	return &models.RoutingResponse{
		AssignedReviewer: best.Username,
		Confidence:       score,
		Reason:           reason,
	}, nil
}

// selectBestReviewer scores and selects the optimal reviewer
func (s *RoutingService) selectBestReviewer(pr *models.PullRequest, reviewers []*models.Reviewer, files []string) (*models.Reviewer, float64, string) {
	type scoredReviewer struct {
		reviewer *models.Reviewer
		score    float64
		reason   string
	}

	var scored []scoredReviewer

	for _, r := range reviewers {
		// Skip author (can't review own code)
		if r.Username == pr.Author {
			continue
		}

		score := 0.0
		reasons := []string{}

		// 1. Capacity score (0-40 points): favor reviewers with more free capacity
		capacityRatio := 1.0 - float64(r.CurrentLoad)/float64(r.MaxLoad)
		capacityScore := capacityRatio * 40.0
		score += capacityScore
		reasons = append(reasons, fmt.Sprintf("capacity=%.0f%%", capacityRatio*100))

		// 2. Expertise score (0-40 points): match files to reviewer expertise
		expertiseScore := s.computeExpertiseScore(r.Username, files)
		score += expertiseScore * 40.0
		if expertiseScore > 0.5 {
			reasons = append(reasons, "expertise match")
		}

		// 3. Workload balance (0-20 points): penalize overloaded reviewers
		recentReviews := r.CurrentLoad
		workloadScore := math.Max(0, 20.0-float64(recentReviews)*5.0)
		score += workloadScore

		// 4. Speed bonus (0-10 points): faster reviewers get priority for complex PRs
		if pr.ComplexityScore > 0.7 && r.AvgReviewTime < 60 {
			score += 10.0
			reasons = append(reasons, "fast reviewer")
		}

		scored = append(scored, scoredReviewer{
			reviewer: r,
			score:    score / 100.0, // normalize to 0-1
			reason:   strings.Join(reasons, ", "),
		})
	}

	if len(scored) == 0 {
		// Fallback: return first available reviewer
		return reviewers[0], 0.5, "fallback assignment"
	}

	// Sort by score (highest first)
	best := scored[0]
	for _, s := range scored[1:] {
		if s.score > best.score {
			best = s
		}
	}

	return best.reviewer, best.score, best.reason
}

// computeExpertiseScore calculates how well a reviewer matches the PR files
func (s *RoutingService) computeExpertiseScore(username string, files []string) float64 {
	if len(files) == 0 {
		return 0.5 // neutral score when no files provided
	}

	expertise, err := s.pg.GetReviewerExpertise(username)
	if err != nil || len(expertise) == 0 {
		return 0.3 // slight penalty for unknown expertise
	}

	totalScore := 0.0
	matches := 0

	for _, f := range files {
		for _, e := range expertise {
			if matchesPattern(f, e.FilePattern) {
				totalScore += e.ExpertiseScore
				matches++
				break
			}
		}
	}

	if matches == 0 {
		return 0.3
	}

	return totalScore / float64(len(files))
}

// matchesPattern checks if a filename matches a glob-like pattern
func matchesPattern(filename, pattern string) bool {
	matched, err := filepath.Match(pattern, filepath.Base(filename))
	if err != nil {
		return false
	}
	if matched {
		return true
	}
	// Check directory prefix
	if strings.HasSuffix(pattern, "/*") {
		dir := strings.TrimSuffix(pattern, "/*")
		return strings.HasPrefix(filename, dir+"/")
	}
	return strings.Contains(filename, pattern)
}

// routingLoop processes the PR queue continuously
func (s *RoutingService) routingLoop(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	s.logger.Println("Routing loop started")

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.processQueue(ctx)
		}
	}
}

func (s *RoutingService) processQueue(ctx context.Context) {
	queueLen, err := s.redis.GetQueueLength(ctx)
	if err != nil || queueLen == 0 {
		return
	}

	s.logger.Printf("Processing queue: %d PRs pending", queueLen)

	// Get available reviewers first
	reviewers, err := s.pg.GetAvailableReviewers()
	if err != nil || len(reviewers) == 0 {
		s.logger.Println("No available reviewers, skipping queue processing")
		return
	}

	// Process up to N PRs per cycle
	prIDs, err := s.redis.GetQueuedPRs(ctx)
	if err != nil {
		return
	}

	processed := 0
	for _, prID := range prIDs {
		if processed >= len(reviewers) {
			break // don't assign more than available capacity
		}

		pr, err := s.pg.GetPR(prID)
		if err != nil {
			s.redis.RemoveFromQueue(ctx, prID) // stale ID
			continue
		}

		if pr.Status != "open" {
			s.redis.RemoveFromQueue(ctx, prID) // already handled
			continue
		}

		files, _ := s.pg.GetPRFiles(prID)
		fileNames := make([]string, len(files))
		for i, f := range files {
			fileNames[i] = f.Filename
		}

		_, err = s.routePR(ctx, prID, fileNames)
		if err != nil {
			s.logger.Printf("Failed to route PR %d: %v", prID, err)
			continue
		}
		processed++
	}

	if processed > 0 {
		s.logger.Printf("Routed %d PRs from queue", processed)
	}
}

func (s *RoutingService) triggerNotification(pr *models.PullRequest, reviewer *models.Reviewer) {
	notifURL := fmt.Sprintf("http://localhost:%d/notify", s.cfg.NotificationServicePort)
	req := models.NotificationRequest{
		PRID:             pr.ID,
		RepoOwner:        pr.RepoOwner,
		RepoName:         pr.RepoName,
		PRNumber:         pr.PRNumber,
		Title:            pr.Title,
		Author:           pr.Author,
		AssignedReviewer: reviewer.Username,
		ComplexityScore:  pr.ComplexityScore,
		EstimatedMinutes: pr.EstimatedMinutes,
		URL:              fmt.Sprintf("https://github.com/%s/%s/pull/%d", pr.RepoOwner, pr.RepoName, pr.PRNumber),
	}

	data, _ := json.Marshal(req)
	resp, err := http.Post(notifURL, "application/json", bytes.NewReader(data))
	if err != nil {
		s.logger.Printf("Failed to send notification for PR %d: %v", pr.ID, err)
		return
	}
	defer resp.Body.Close()
}