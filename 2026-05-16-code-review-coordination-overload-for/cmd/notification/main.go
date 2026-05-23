package main

import (
	"bytes"
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
)

type NotificationService struct {
	cfg    *config.Config
	logger *log.Logger
}

// Slack message structures
type SlackMessage struct {
	Text        string            `json:"text,omitempty"`
	Attachments []SlackAttachment `json:"attachments,omitempty"`
}

type SlackAttachment struct {
	Color     string       `json:"color"`
	Title     string       `json:"title"`
	TitleLink string       `json:"title_link,omitempty"`
	Text      string       `json:"text"`
	Fields    []SlackField `json:"fields"`
	Footer    string       `json:"footer"`
	Ts        int64        `json:"ts"`
}

type SlackField struct {
	Title string `json:"title"`
	Value string `json:"value"`
	Short bool   `json:"short"`
}

func main() {
	logger := log.New(os.Stdout, "[notification] ", log.LstdFlags|log.Lshortfile)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("Failed to load config: %v", err)
	}

	svc := &NotificationService{
		cfg:    cfg,
		logger: logger,
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", svc.healthHandler)
	r.Post("/notify", svc.notifyHandler)
	r.Post("/notify/test", svc.testNotifyHandler)

	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.NotificationServicePort),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		logger.Printf("Notification service starting on port %d", cfg.NotificationServicePort)
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
	logger.Println("Notification service stopped")
}

func (s *NotificationService) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "notification"})
}

func (s *NotificationService) notifyHandler(w http.ResponseWriter, r *http.Request) {
	var req models.NotificationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	s.logger.Printf("Sending notification: PR #%d assigned to %s", req.PRNumber, req.AssignedReviewer)

	var notifyErr error

	if s.cfg.SlackWebhookURL != "" {
		notifyErr = s.sendSlackNotification(req)
		if notifyErr != nil {
			s.logger.Printf("Slack notification failed: %v", notifyErr)
		} else {
			s.logger.Printf("Slack notification sent for PR #%d", req.PRNumber)
		}
	} else {
		s.logNotification(req)
	}

	w.Header().Set("Content-Type", "application/json")
	if notifyErr != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"status": "error", "message": notifyErr.Error()})
		return
	}
	json.NewEncoder(w).Encode(map[string]string{"status": "sent"})
}

func (s *NotificationService) testNotifyHandler(w http.ResponseWriter, r *http.Request) {
	testReq := models.NotificationRequest{
		PRID:             1,
		RepoOwner:        "testorg",
		RepoName:         "testrepo",
		PRNumber:         42,
		Title:            "Test: Add authentication middleware",
		Author:           "dev-alice",
		AssignedReviewer: "dev-bob",
		ComplexityScore:  0.72,
		EstimatedMinutes: 45,
		URL:              "https://github.com/testorg/testrepo/pull/42",
	}

	if s.cfg.SlackWebhookURL != "" {
		if err := s.sendSlackNotification(testReq); err != nil {
			http.Error(w, fmt.Sprintf("Slack test failed: %v", err), http.StatusInternalServerError)
			return
		}
	} else {
		s.logNotification(testReq)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "test sent"})
}

func (s *NotificationService) sendSlackNotification(req models.NotificationRequest) error {
	color := "#36a64f"
	if req.ComplexityScore > 0.7 {
		color = "#d32f2f"
	} else if req.ComplexityScore > 0.4 {
		color = "#ff9800"
	}

	riskLabel := "🟢 Low"
	if req.ComplexityScore > 0.7 {
		riskLabel = "🔴 High"
	} else if req.ComplexityScore > 0.4 {
		riskLabel = "🟡 Medium"
	}

	estimatedStr := fmt.Sprintf("%d min", req.EstimatedMinutes)
	if req.EstimatedMinutes >= 60 {
		hours := req.EstimatedMinutes / 60
		mins := req.EstimatedMinutes % 60
		if mins > 0 {
			estimatedStr = fmt.Sprintf("%dh %dm", hours, mins)
		} else {
			estimatedStr = fmt.Sprintf("%dh", hours)
		}
	}

	msg := SlackMessage{
		Text: fmt.Sprintf("👀 *Code review requested* — @%s, you're up!", req.AssignedReviewer),
		Attachments: []SlackAttachment{
			{
				Color:     color,
				Title:     fmt.Sprintf("[%s/%s] #%d: %s", req.RepoOwner, req.RepoName, req.PRNumber, req.Title),
				TitleLink: req.URL,
				Text:      fmt.Sprintf("Submitted by *%s*", req.Author),
				Fields: []SlackField{
					{Title: "Assigned To", Value: req.AssignedReviewer, Short: true},
					{Title: "Risk Level", Value: riskLabel, Short: true},
					{Title: "Complexity", Value: fmt.Sprintf("%.0f%%", req.ComplexityScore*100), Short: true},
					{Title: "Est. Review Time", Value: estimatedStr, Short: true},
				},
				Footer: "Code Review Coordinator",
				Ts:     time.Now().Unix(),
			},
		},
	}

	payload, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal Slack message: %w", err)
	}

	resp, err := http.Post(s.cfg.SlackWebhookURL, "application/json", bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to send Slack request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("slack returned status %d", resp.StatusCode)
	}
	return nil
}

func (s *NotificationService) logNotification(req models.NotificationRequest) {
	s.logger.Printf(`
=== NOTIFICATION (DRY RUN — set SLACK_WEBHOOK_URL to enable) ===
PR:         #%d — %s
Repo:       %s/%s
Author:     %s
Reviewer:   %s
Complexity: %.0f%%  |  Est. Time: %d min
URL:        %s
================================================================`,
		req.PRNumber, req.Title,
		req.RepoOwner, req.RepoName,
		req.Author,
		req.AssignedReviewer,
		req.ComplexityScore*100, req.EstimatedMinutes,
		req.URL,
	)
}