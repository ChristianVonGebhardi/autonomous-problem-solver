package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/actions"
	"github.com/cloudcircuitbreaker/mvp/internal/engine"
	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"github.com/cloudcircuitbreaker/mvp/internal/policy"
	"github.com/cloudcircuitbreaker/mvp/internal/queue"
	"github.com/cloudcircuitbreaker/mvp/internal/simulator"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	log.Println("=== Cloud Spending Circuit Breaker - Demo Server ===")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		log.Printf("Received signal: %v, shutting down...", sig)
		cancel()
	}()

	// Set up in-memory store (demo mode — no DB required)
	store := simulator.NewSpendingStore()

	// Seed historical data for baseline
	sim := simulator.NewSimulator(store)
	sim.SeedHistoricalData()

	// Set up message queue (in-memory for demo)
	mq := queue.NewInMemoryQueue()

	// Set up action executor (dry-run mode)
	executor := actions.NewActionExecutor("", true)

	// Wire up breach handler: queue -> executor
	mq.Subscribe(func(event models.BreachEvent) error {
		return executor.Execute(event)
	})

	// Load policies from file or use defaults
	var policies []models.Policy
	policyFile := os.Getenv("POLICY_FILE")
	if policyFile == "" {
		policyFile = "configs/policies.yaml"
	}

	loadedPolicies, err := policy.LoadFromFile(policyFile)
	if err != nil {
		log.Printf("Could not load policy file %s: %v — using default policies", policyFile, err)
		policies = defaultPolicies()
	} else {
		policies = loadedPolicies
		log.Printf("Loaded %d policies from %s", len(policies), policyFile)
	}

	// Create circuit breaker engine
	cbEngine, err := engine.NewCircuitBreakerEngine(store, func(event models.BreachEvent) error {
		return mq.PublishBreachEvent(event)
	})
	if err != nil {
		log.Fatalf("create circuit breaker engine: %v", err)
	}

	// Reduce eval interval for demo visibility
	cbEngine.SetEvalInterval(5 * time.Second)

	if err := cbEngine.LoadPolicies(policies); err != nil {
		log.Fatalf("load policies: %v", err)
	}

	// Start simulator generating real-time metrics
	sim.Start(ctx)

	// Start circuit breaker engine
	go cbEngine.Run(ctx)

	// Print status dashboard every 15 seconds
	statusTicker := time.NewTicker(15 * time.Second)
	defer statusTicker.Stop()

	// Initial status
	sim.PrintStatus(ctx)

	for {
		select {
		case <-ctx.Done():
			log.Println("Server shutdown complete")
			return
		case <-statusTicker.C:
			sim.PrintStatus(ctx)
			printBreachSummary(executor)
		}
	}
}

func printBreachSummary(executor *actions.ActionExecutor) {
	notifications := executor.GetNotifications()
	if len(notifications) == 0 {
		return
	}

	fmt.Printf("\n📊 Breach Events (last %d notifications):\n", len(notifications))
	start := 0
	if len(notifications) > 5 {
		start = len(notifications) - 5
	}
	for _, n := range notifications[start:] {
		status := "✅"
		if !n.Success {
			status = "❌"
		}
		fmt.Printf("  %s [%s] team=%s action=%s\n",
			status,
			n.Timestamp.Format("15:04:05"),
			n.Event.Team,
			n.Action,
		)
	}
}

// defaultPolicies returns hardcoded demo policies when no file is found
func defaultPolicies() []models.Policy {
	return []models.Policy{
		{
			ID:              "platform-daily-limit",
			Name:            "Platform Team Daily Spend Limit",
			Description:     "Alert when platform team exceeds $50/day",
			Team:            "platform",
			Project:         "*",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 50.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
			},
		},
		{
			ID:              "data-hourly-limit",
			Name:            "Data Team Hourly Runaway Guard",
			Description:     "Halt when data team hourly rate exceeds $10/hr",
			Team:            "data",
			Project:         "*",
			Enabled:         true,
			CELExpression:   "hourly_rate > 10.0",
			ThresholdAmount: 10.0,
			TimeWindow:      "1h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
				{Type: "halt", Severity: "critical"},
			},
		},
		{
			ID:              "data-daily-limit",
			Name:            "Data Team Daily Spend Limit",
			Description:     "Alert when data team exceeds $100/day",
			Team:            "data",
			Project:         "ml-training",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 100.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
				{Type: "halt", Severity: "critical"},
			},
		},
	}
}