package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
)

type AssignmentNotification struct {
	PRID               string          `json:"pr_id"`
	PRTitle            string          `json:"pr_title"`
	PRRepo             string          `json:"pr_repo"`
	PRAuthor           string          `json:"pr_author"`
	ComplexityScore    float64         `json:"complexity_score"`
	RiskScore          float64         `json:"risk_score"`
	EstimatedMinutes   int             `json:"estimated_minutes"`
	Assignees          []AssigneeInfo  `json:"assignees"`
}

type AssigneeInfo struct {
	ReviewerID   string  `json:"reviewer_id"`
	ReviewerName string  `json:"reviewer_name"`
	Username     string  `json:"username"`
	SlackUserID  string  `json:"slack_user_id"`
	Score        float64 `json:"score"`
	Reason       string  `json:"reason"`
}

type SlackMessage struct {
	Text   string       `json:"text,omitempty"`
	Blocks []SlackBlock `json:"blocks,omitempty"`
}

type SlackBlock struct {
	Type string      `json:"type"`
	Text *SlackText  `json:"text,omitempty"`
	Fields []SlackText `json:"fields,omitempty"`
}

type SlackText struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type Server struct {
	db           *pgxpool.Pool
	nc           *nats.Conn
	js           nats.JetStreamContext
	slackWebhook string
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

	srv := &Server{
		db:           dbPool,
		nc:           nc,
		js:           js,
		slackWebhook: getEnv("SLACK_WEBHOOK_URL", ""),
	}

	go srv.subscribeAssignments()

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", srv.handleHealth)
	r.Post("/notify", srv.handleManualNotify)
	r.Get("/notifications", srv.handleGetNotifications)

	log.Println("Notification service starting on :8083")
	if err := http.ListenAndServe(":8083", r); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func (s *Server) subscribeAssignments() {
	time.Sleep(3 * time.Second)

	_, err := s.js.Subscribe(
		"pr.assigned.notify",
		func(msg *nats.Msg) {
			var notif AssignmentNotification
			if err := json.Unmarshal(msg.Data, &notif); err != nil {
				log.Printf("Failed to parse assignment notification: %v", err)
				msg.Nak()
				return
			}

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()

			if err := s.sendNotifications(ctx, notif); err != nil {
				log.Printf("Failed to send notifications: %v", err)
			}

			msg.Ack()
		},
		nats.Durable("notification-worker"),
		nats.ManualAck(),
	)
	if err != nil {
		log.Printf("Failed to subscribe: %v", err)
	} else {
		log.Println("Notification service subscribed to pr.assigned.notify")
	}
}

func (s *Server) sendNotifications(ctx context.Context, notif AssignmentNotification) error {
	for _, assignee := range notif.Assignees {
		// Build notification message
		msg := s.buildReviewRequestMessage(notif, assignee)

		// Log to database
		s.logNotification(ctx, notif, assignee, msg)

		// Send to Slack if configured
		if s.slackWebhook != "" && assignee.SlackUserID != "" {
			if err := s.sendSlackNotification(notif, assignee); err != nil {
				log.Printf("Slack notification failed for %s: %v", assignee.Username, err)
			}
		}

		log.Printf("📬 Notification sent to %s for PR: %s", assignee.ReviewerName, notif.PRTitle)
		log.Printf("   Message: %s", msg)
	}

	return nil
}

func (s *Server) buildReviewRequestMessage(notif AssignmentNotification, assignee AssigneeInfo) string {
	complexity := "🟢 Low"
	if notif.ComplexityScore >= 7 {
		complexity = "🔴 High"
	} else if notif.ComplexityScore >= 4 {
		complexity = "🟡 Medium"
	}

	risk := "🟢 Low"
	if notif.RiskScore >= 7 {
		risk = "🔴 High"
	} else if notif.RiskScore >= 4 {
		risk = "🟡 Medium"
	}

	return fmt.Sprintf(
		"Review request for %s:\n  PR: %s\n  Repo: %s\n  Author: @%s\n  Complexity: %s (%.1f/10)\n  Risk: %s (%.1f/10)\n  Estimated time: ~%d min\n  Routing reason: %s",
		assignee.ReviewerName,
		notif.PRTitle,
		notif.PRRepo,
		notif.PRAuthor,
		complexity, notif.ComplexityScore,
		risk, notif.RiskScore,
		notif.EstimatedMinutes,
		assignee.Reason,
	)
}

func (s *Server) sendSlackNotification(notif AssignmentNotification, assignee AssigneeInfo) error {
	complexityEmoji := "🟢"
	if notif.ComplexityScore >= 7 {
		complexityEmoji = "🔴"
	} else if notif.ComplexityScore >= 4 {
		complexityEmoji = "🟡"
	}

	riskEmoji := "🟢"
	if notif.RiskScore >= 7 {
		riskEmoji = "🔴"
	} else if notif.RiskScore >= 4 {
		riskEmoji = "🟡"
	}

	slackMsg := SlackMessage{
		Blocks: []SlackBlock{
			{
				Type: "section",
				Text: &SlackText{
					Type: "mrkdwn",
					Text: fmt.Sprintf("👀 *Code Review Request* for <@%s>", assignee.SlackUserID),
				},
			},
			{
				Type: "section",
				Fields: []SlackText{
					{Type: "mrkdwn", Text: fmt.Sprintf("*PR:*\n%s", notif.PRTitle)},
					{Type: "mrkdwn", Text: fmt.Sprintf("*Repository:*\n`%s`", notif.PRRepo)},
					{Type: "mrkdwn", Text: fmt.Sprintf("*Author:*\n@%s", notif.PRAuthor)},
					{Type: "mrkdwn", Text: fmt.Sprintf("*Est. Time:*\n~%d minutes", notif.EstimatedMinutes)},
					{Type: "mrkdwn", Text: fmt.Sprintf("*Complexity:*\n%s %.1f/10", complexityEmoji, notif.ComplexityScore)},
					{Type: "mrkdwn", Text: fmt.Sprintf("*Risk Level:*\n%s %.1f/10", riskEmoji, notif.RiskScore)},
				},
			},
			{
				Type: "section",
				Text: &SlackText{
					Type: "mrkdwn",
					Text: fmt.Sprintf("_Routing reason: %s_", assignee.Reason),
				},
			},
		},
	}

	payload, err := json.Marshal(slackMsg)
	if err != nil {
		return err
	}

	resp, err := http.Post(s.slackWebhook, "application/json", bytes.NewBuffer(payload))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("slack returned status %d", resp.StatusCode)
	}

	return nil
}

func (s *Server) logNotification(ctx context.Context, notif AssignmentNotification,
	assignee AssigneeInfo, msg string) {

	// Find assignment ID
	var assignmentID string
	s.db.QueryRow(ctx, `
		SELECT id FROM review_assignments 
		WHERE pr_id = $1 AND reviewer_id = $2 
		ORDER BY created_at DESC LIMIT 1`,
		notif.PRID, assignee.ReviewerID).Scan(&assignmentID)

	if assignmentID == "" {
		log.Printf("Warning: could not find assignment for notification logging")
		return
	}

	channel := "log"
	if s.slackWebhook != "" {
		channel = "slack"
	}

	s.db.Exec(ctx, `
		INSERT INTO notification_log (assignment_id, channel, recipient, message_preview, status)
		VALUES ($1, $2, $3, $4, 'sent')`,
		assignmentID, channel, assignee.Username, truncate(msg, 500),
	)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "notification"})
}

func (s *Server) handleManualNotify(w http.ResponseWriter, r *http.Request) {
	var notif AssignmentNotification
	if err := json.NewDecoder(r.Body).Decode(&notif); err != nil {
		http.Error(w, "Invalid body", http.StatusBadRequest)
		return
	}

	if err := s.sendNotifications(r.Context(), notif); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "sent"})
}

func (s *Server) handleGetNotifications(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	rows, err := s.db.Query(ctx, `
		SELECT nl.id, nl.channel, nl.recipient, nl.message_preview, nl.status, nl.sent_at,
		       pr.title as pr_title
		FROM notification_log nl
		JOIN review_assignments ra ON ra.id = nl.assignment_id
		JOIN pull_requests pr ON pr.id = ra.pr_id
		ORDER BY nl.sent_at DESC
		LIMIT 50`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type NotificationRecord struct {
		ID             string    `json:"id"`
		Channel        string    `json:"channel"`
		Recipient      string    `json:"recipient"`
		MessagePreview string    `json:"message_preview"`
		Status         string    `json:"status"`
		SentAt         time.Time `json:"sent_at"`
		PRTitle        string    `json:"pr_title"`
	}

	var records []NotificationRecord
	for rows.Next() {
		var rec NotificationRecord
		if err := rows.Scan(&rec.ID, &rec.Channel, &rec.Recipient,
			&rec.MessagePreview, &rec.Status, &rec.SentAt, &rec.PRTitle); err != nil {
			continue
		}
		records = append(records, rec)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(records)
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