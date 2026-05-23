package actions

import (
	"fmt"
	"log"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
)

// ActionExecutor handles breach event actions
type ActionExecutor struct {
	slackWebhook  string
	dryRun        bool
	notifications []NotificationRecord
}

// NotificationRecord tracks sent notifications
type NotificationRecord struct {
	Timestamp time.Time
	Event     models.BreachEvent
	Action    string
	Success   bool
	Message   string
}

// NewActionExecutor creates a new executor
func NewActionExecutor(slackWebhook string, dryRun bool) *ActionExecutor {
	return &ActionExecutor{
		slackWebhook: slackWebhook,
		dryRun:       dryRun,
	}
}

// Execute processes a breach event and runs all configured actions
func (e *ActionExecutor) Execute(event models.BreachEvent) error {
	log.Printf("🚨 BREACH EVENT: policy=%s team=%s severity=%s actual=$%.2f threshold=$%.2f",
		event.PolicyID, event.Team, event.Severity, event.ActualValue, event.Threshold)

	for _, actionType := range event.ActionsTaken {
		if err := e.executeAction(event, actionType); err != nil {
			log.Printf("ERROR: executing action %s: %v", actionType, err)
		}
	}

	return nil
}

// executeAction runs a specific action type
func (e *ActionExecutor) executeAction(event models.BreachEvent, actionType string) error {
	record := NotificationRecord{
		Timestamp: time.Now(),
		Event:     event,
		Action:    actionType,
	}

	var err error
	switch actionType {
	case "notify":
		err = e.sendNotification(event)
		record.Message = fmt.Sprintf("Notification sent for breach: %s", event.Message)
	case "throttle":
		err = e.throttleResources(event)
		record.Message = fmt.Sprintf("Throttle action for team=%s resource=%s", event.Team, event.ResourceID)
	case "halt":
		err = e.haltResources(event)
		record.Message = fmt.Sprintf("HALT action for team=%s resource=%s", event.Team, event.ResourceID)
	case "terminate":
		err = e.terminateResources(event)
		record.Message = fmt.Sprintf("TERMINATE action for team=%s resource=%s", event.Team, event.ResourceID)
	default:
		log.Printf("WARN: unknown action type: %s", actionType)
		return nil
	}

	record.Success = err == nil
	e.notifications = append(e.notifications, record)
	return err
}

// sendNotification logs / sends a Slack notification
func (e *ActionExecutor) sendNotification(event models.BreachEvent) error {
	msg := fmt.Sprintf(
		"[CIRCUIT BREAKER] 🚨 Spending Alert\n"+
			"Team: %s | Project: %s\n"+
			"Severity: %s\n"+
			"Actual: $%.2f | Threshold: $%.2f\n"+
			"Message: %s",
		event.Team, event.Project,
		event.Severity,
		event.ActualValue, event.Threshold,
		event.Message,
	)

	log.Println("📣 NOTIFICATION:", msg)

	if e.slackWebhook != "" && !e.dryRun {
		return sendSlackMessage(e.slackWebhook, msg)
	}

	if e.dryRun {
		log.Println("[DRY RUN] Would send Slack notification")
	}

	return nil
}

// throttleResources simulates downscaling resources
func (e *ActionExecutor) throttleResources(event models.BreachEvent) error {
	if e.dryRun {
		log.Printf("[DRY RUN] Would throttle resource %s in team %s", event.ResourceID, event.Team)
		return nil
	}

	// In production: call cloud API to downscale instance type or reduce replicas
	log.Printf("⚡ THROTTLE: Would downscale resource %s (team=%s, project=%s)",
		event.ResourceID, event.Team, event.Project)

	return nil
}

// haltResources simulates stopping resources
func (e *ActionExecutor) haltResources(event models.BreachEvent) error {
	if e.dryRun {
		log.Printf("[DRY RUN] Would HALT resource %s in team %s", event.ResourceID, event.Team)
		return nil
	}

	// In production: call cloud API to stop the instance
	log.Printf("🛑 HALT: Would stop resource %s (team=%s, project=%s)",
		event.ResourceID, event.Team, event.Project)

	return nil
}

// terminateResources simulates terminating resources (with safeguards)
func (e *ActionExecutor) terminateResources(event models.BreachEvent) error {
	if e.dryRun {
		log.Printf("[DRY RUN] Would TERMINATE resource %s in team %s", event.ResourceID, event.Team)
		return nil
	}

	// In production: requires additional approval workflow
	log.Printf("💀 TERMINATE: Would terminate resource %s (team=%s, project=%s) — requires approval",
		event.ResourceID, event.Team, event.Project)

	return nil
}

// GetNotifications returns all notification records
func (e *ActionExecutor) GetNotifications() []NotificationRecord {
	return e.notifications
}

// sendSlackMessage sends a message to Slack via webhook
func sendSlackMessage(webhookURL, message string) error {
	// In production: send HTTP POST to Slack webhook
	// For MVP, just log it
	log.Printf("Slack message: %s", message)
	return nil
}