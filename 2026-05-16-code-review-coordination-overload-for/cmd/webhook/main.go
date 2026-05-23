package main

import (
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
	cfg     *config.Config
	pg      *store.PostgresStore
	redis   *store.RedisStore
	logger  *log.Logger
}

// GitHub webhook event types
type GitHubPREvent struct {
	Action      string `json:"action"`
	Number      int    `json:"number"`
	PullRequest struct {
		Number int    `json:"number"`
		Title  string `json:"title"`
		State  string `json:"state"`
		User   struct {
			Login string `json:"login"`
		} `json:"user"`
		Additions int `json:"additions"`
		Deletions int `json:"deletions"`
		ChangedFiles int `json:"changed_files"`
		Head struct {
			SHA  string `json:"sha"`
			Ref  string `json:"ref"`
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
	r.Post("/api/prs", h.createPRHandler)           // Manual PR creation for testing
	r.Get("/api/prs", h.listPRsHandler)
	r.Put("/api/prs/{id}/status", h.updatePRStatusHandler)

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

	// For new PRs, enqueue for analysis and routing
	if event.Action == "opened" || event.Action == "reopened" {
		ctx := r.Context()
		// Priority = lines changed (more lines = higher priority to get reviewed quickly)
		priority := float64(pr.LinesAdded + pr.LinesDeleted)
		if err := h.redis.EnqueuePR(ctx, pr.ID, priority); err != nil {
			h.logger.Printf("Failed to enqueue PR: %v", err)
		}
		h.logger.Printf("Enqueued PR %d for analysis", pr.ID)

		// Trigger analysis via internal HTTP call (non-blocking)
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
	resp, err := http.Post(analysisURL, "application/json", 
		io.NopCloser(
			func() io.Reader {
				return &jsonReader{data: data}
			}(),
		),
	)
	if err != nil {
		h.logger.Printf("Failed to trigger analysis for PR %d: %v", pr.ID, err)
		return
	}
	defer resp.Body.Close()
	h.logger.Printf("Analysis triggered for PR %d, response: %d", pr.ID, resp.StatusCode)
}

type jsonReader struct {
	data []byte
	pos  int
}

func (jr *jsonReader) Read(p []byte) (n int, err error) {
	if jr.pos >= len(jr.data) {
		return 0, io.EOF
	}
	n = copy(p, jr.data[jr.pos:])
	jr.pos += n
	return n, nil
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

	if err := h.pg.UpsertPR(&pr); err != nil {
		h.logger.Printf("Failed to create PR: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Enqueue for routing
	ctx := r.Context()
	priority := float64(pr.LinesAdded + pr.LinesDeleted + pr.FilesChanged*10)
	h.redis.EnqueuePR(ctx, pr.ID, priority)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
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