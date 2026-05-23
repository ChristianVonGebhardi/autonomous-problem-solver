package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
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

type WebhookHandler struct {
	cfg    *config.Config
	pg     *store.PostgresStore
	redis  *store.RedisStore
	logger *log.Logger
}

// GitHub webhook event types
type GitHubPREvent struct {
	Action      string `json:"action"`
	Number      int    `json:"number"`
	PullRequest struct {
		Number       int    `json:"number"`
		Title        string `json:"title"`
		State        string `json:"state"`
		User         struct {
			Login string `json:"login"`
		} `json:"user"`
		Additions    int `json:"additions"`
		Deletions    int `json:"deletions"`
		ChangedFiles int `json:"changed_files"`
		Head         struct {
			SHA string `json:"sha"`
			Ref string `json:"ref"`
		} `json:"head"`
		HTMLURL string `json:"html_url"`
	} `json:"pull_request"`
	Repository struct {
		Name  string `json:"name"`
		Owner struct {
			Login string `json:"login"`
		} `json:"owner"`
	} `json:"repository"`
	Review struct {
		State string `json:"state"`
		User  struct {
			Login string `json:"login"`
		} `json:"user"`
	} `json:"review"`
}

func main() {
	logger := log.New(os.Stdout, "[webhook] ", log.LstdFlags|log.Lshortfile)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("Failed to load config: %v", err)
	}

	pg, err := store.NewPostgresStore(cfg.PostgresConnectionString())
	if err != nil {
		logger.Fatalf("Failed to connect to PostgreSQL: %v", err)
	}
	defer pg.Close()

	if err := pg.Migrate(); err != nil {
		logger.Fatalf("Migration failed: %v", err)
	}

	redis, err := store.NewRedisStore(cfg.RedisAddress())
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redis.Close()

	h := &WebhookHandler{
		cfg:    cfg,
		pg:     pg,
		redis:  redis,
		logger: logger,
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestID)

	r.Get("/health", h.healthHandler)
	r.Post("/webhooks/github", h.githubWebhookHandler)

	// REST API for manual testing and service-to-service calls
	r.Post("/api/prs", h.createPRHandler)
	r.Get("/api/prs", h.listPRsHandler)
	r.Get("/api/prs/{id}", h.getPRHandler)
	r.Put("/api/prs/{id}/status", h.updatePRStatusHandler)
	r.Patch("/api/prs/{id}/analysis", h.updatePRAnalysisHandler) // Called by Python analysis service

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.WebhookServicePort),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		logger.Printf("Webhook service starting on port %d", cfg.WebhookServicePort)
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
	logger.Println("Webhook service stopped")
}

func (h *WebhookHandler) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "webhook"})
}

func (h *WebhookHandler) githubWebhookHandler(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	eventType := r.Header.Get("X-GitHub-Event")
	h.logger.Printf("Received GitHub event: %s", eventType)

	switch eventType {
	case "pull_request":
		h.handlePREvent(w, r, body)
	case "pull_request_review":
		h.handleReviewEvent(w, r, body)
	default:
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ignored", "event": eventType})
	}
}

func (h *WebhookHandler) handlePREvent(w http.ResponseWriter, r *http.Request, body []byte) {
	var event GitHubPREvent
	if err := json.Unmarshal(body, &event); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	pr := &models.PullRequest{
		RepoOwner:    event.Repository.Owner.Login,
		RepoName:     event.Repository.Name,
		PRNumber:     event.PullRequest.Number,
		Title:        event.PullRequest.Title,
		Author:       event.PullRequest.User.Login,
		LinesAdded:   event.PullRequest.Additions,
		LinesDeleted: event.PullRequest.Deletions,
		FilesChanged: event.PullRequest.ChangedFiles,
	}

	switch event.Action {
	case "opened", "reopened":
		pr.Status = "open"
	case "closed":
		pr.Status = "closed"
		if event.PullRequest.State == "closed" {
			pr.Status = "merged"
		}
	case "synchronize":
		pr.Status = "open"
	default:
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ignored", "action": event.Action})
		return
	}

	if err := h.pg.UpsertPR(pr); err != nil {
		h.logger.Printf("Failed to upsert PR: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	h.logger.Printf("Stored PR #%d from %s/%s (action: %s)", pr.PRNumber, pr.RepoOwner, pr.RepoName, event.Action)

	if event.Action == "opened" || event.Action == "reopened" {
		ctx := r.Context()
		priority := float64(pr.LinesAdded + pr.LinesDeleted)
		if err := h.redis.EnqueuePR(ctx, pr.ID, priority); err != nil {
			h.logger.Printf("Failed to enqueue PR: %v", err)
		}
		go h.triggerAnalysis(pr)
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "processed",
		"pr_id":  pr.ID,
		"action": event.Action,
	})
}

func (h *WebhookHandler) handleReviewEvent(w http.ResponseWriter, r *http.Request, body []byte) {
	var event GitHubPREvent
	if err := json.Unmarshal(body, &event); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	h.logger.Printf("Review event: %s by %s", event.Review.State, event.Review.User.Login)

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "processed"})
}

func (h *WebhookHandler) triggerAnalysis(pr *models.PullRequest) {
	analysisURL := fmt.Sprintf("http://localhost:%d/analyze", h.cfg.AnalysisServicePort)
	req := models.AnalysisRequest{
		PRID:         pr.ID,
		LinesAdded:   pr.LinesAdded,
		LinesDeleted: pr.LinesDeleted,
		FilesChanged: pr.FilesChanged,
		Author:       pr.Author,
	}

	data, _ := json.Marshal(req)
	resp, err := http.Post(analysisURL, "application/json", bytes.NewReader(data))
	if err != nil {
		h.logger.Printf("Failed to trigger analysis for PR %d: %v", pr.ID, err)
		return
	}
	defer resp.Body.Close()
	h.logger.Printf("Analysis triggered for PR %d, response: %d", pr.ID, resp.StatusCode)
}

func (h *WebhookHandler) createPRHandler(w http.ResponseWriter, r *http.Request) {
	var pr models.PullRequest
	if err := json.NewDecoder(r.Body).Decode(&pr); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if pr.Status == "" {
		pr.Status = "open"
	}
	if pr.RepoOwner == "" {
		pr.RepoOwner = "demo"
	}
	if pr.RepoName == "" {
		pr.RepoName = "repo"
	}
	if pr.PRNumber == 0 {
		// Auto-assign a PR number based on timestamp
		pr.PRNumber = int(time.Now().UnixNano() % 100000)
	}

	if err := h.pg.UpsertPR(&pr); err != nil {
		h.logger.Printf("Failed to create PR: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	ctx := r.Context()
	priority := float64(pr.LinesAdded + pr.LinesDeleted + pr.FilesChanged*10)
	h.redis.EnqueuePR(ctx, pr.ID, priority)

	// Trigger analysis asynchronously
	go h.triggerAnalysis(&pr)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(pr)
}

func (h *WebhookHandler) getPRHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	var id int64
	fmt.Sscanf(idStr, "%d", &id)

	pr, err := h.pg.GetPR(id)
	if err != nil {
		http.Error(w, "PR not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(pr)
}

func (h *WebhookHandler) listPRsHandler(w http.ResponseWriter, r *http.Request) {
	status := r.URL.Query().Get("status")
	prs, err := h.pg.ListPRs(status, 50)
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

func (h *WebhookHandler) updatePRStatusHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	var id int64
	fmt.Sscanf(idStr, "%d", &id)

	var req struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if err := h.pg.UpdatePRStatus(id, req.Status); err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
}

// updatePRAnalysisHandler is called by the Python analysis service
func (h *WebhookHandler) updatePRAnalysisHandler(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	var id int64
	fmt.Sscanf(idStr, "%d", &id)

	var req struct {
		ComplexityScore  float64 `json:"complexity_score"`
		EstimatedMinutes int     `json:"estimated_minutes"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if err := h.pg.UpdatePRAnalysis(id, req.ComplexityScore, req.EstimatedMinutes); err != nil {
		h.logger.Printf("Failed to update PR analysis: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	h.logger.Printf("Updated analysis for PR %d: complexity=%.3f, est=%dmin", id, req.ComplexityScore, req.EstimatedMinutes)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
}