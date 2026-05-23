package engine

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"github.com/google/cel-go/cel"
)

// SpendingFetcher is an interface for querying current spending
type SpendingFetcher interface {
	GetTeamSpending(ctx context.Context, team string, since time.Time) (float64, error)
	GetProjectSpending(ctx context.Context, team, project string, since time.Time) (float64, error)
	GetResourceSpending(ctx context.Context, resourceID string, since time.Time) (float64, error)
}

// BreachHandler is called when a policy breach is detected
type BreachHandler func(event models.BreachEvent) error

// CircuitBreakerEngine evaluates spending policies and fires breach events
type CircuitBreakerEngine struct {
	fetcher       SpendingFetcher
	policies      []models.Policy
	policiesMu    sync.RWMutex
	breachHandler BreachHandler
	evalInterval  time.Duration
	compiledRules map[string]cel.Program
	compiledMu    sync.RWMutex
	env           *cel.Env
}

// NewCircuitBreakerEngine creates a new engine
func NewCircuitBreakerEngine(fetcher SpendingFetcher, breachHandler BreachHandler) (*CircuitBreakerEngine, error) {
	env, err := cel.NewEnv(
		cel.Variable("team_spend", cel.DoubleType),
		cel.Variable("project_spend", cel.DoubleType),
		cel.Variable("resource_spend", cel.DoubleType),
		cel.Variable("hourly_rate", cel.DoubleType),
		cel.Variable("daily_rate", cel.DoubleType),
		cel.Variable("threshold", cel.DoubleType),
		cel.Variable("team", cel.StringType),
		cel.Variable("project", cel.StringType),
		cel.Variable("resource_id", cel.StringType),
	)
	if err != nil {
		return nil, fmt.Errorf("create CEL env: %w", err)
	}

	return &CircuitBreakerEngine{
		fetcher:       fetcher,
		breachHandler: breachHandler,
		evalInterval:  10 * time.Second,
		compiledRules: make(map[string]cel.Program),
		env:           env,
	}, nil
}

// LoadPolicies replaces current policies with new set
func (e *CircuitBreakerEngine) LoadPolicies(policies []models.Policy) error {
	e.policiesMu.Lock()
	defer e.policiesMu.Unlock()

	e.compiledMu.Lock()
	defer e.compiledMu.Unlock()

	// Clear old compiled rules
	e.compiledRules = make(map[string]cel.Program)

	for _, policy := range policies {
		if !policy.Enabled {
			continue
		}

		prog, err := e.compileRule(policy.CELExpression)
		if err != nil {
			log.Printf("WARN: failed to compile policy %s (%s): %v", policy.ID, policy.Name, err)
			continue
		}

		e.compiledRules[policy.ID] = prog
	}

	e.policies = policies
	log.Printf("Loaded %d policies (%d compiled)", len(policies), len(e.compiledRules))
	return nil
}

// compileRule compiles a CEL expression into a program
func (e *CircuitBreakerEngine) compileRule(expression string) (cel.Program, error) {
	ast, iss := e.env.Compile(expression)
	if iss != nil && iss.Err() != nil {
		return nil, fmt.Errorf("compile: %w", iss.Err())
	}

	prog, err := e.env.Program(ast)
	if err != nil {
		return nil, fmt.Errorf("create program: %w", err)
	}

	return prog, nil
}

// EvaluateAll evaluates all enabled policies and fires breach events
func (e *CircuitBreakerEngine) EvaluateAll(ctx context.Context) error {
	e.policiesMu.RLock()
	policies := make([]models.Policy, len(e.policies))
	copy(policies, e.policies)
	e.policiesMu.RUnlock()

	for _, policy := range policies {
		if !policy.Enabled {
			continue
		}

		if err := e.evaluatePolicy(ctx, policy); err != nil {
			log.Printf("ERROR: evaluating policy %s: %v", policy.ID, err)
		}
	}

	return nil
}

// evaluatePolicy evaluates a single policy
func (e *CircuitBreakerEngine) evaluatePolicy(ctx context.Context, policy models.Policy) error {
	window, err := parseTimeWindow(policy.TimeWindow)
	if err != nil {
		return fmt.Errorf("parse time window: %w", err)
	}

	since := time.Now().Add(-window)

	// Fetch spending data
	teamSpend, err := e.fetcher.GetTeamSpending(ctx, policy.Team, since)
	if err != nil {
		return fmt.Errorf("get team spending: %w", err)
	}

	projectSpend, err := e.fetcher.GetProjectSpending(ctx, policy.Team, policy.Project, since)
	if err != nil {
		return fmt.Errorf("get project spending: %w", err)
	}

	// Compute rates
	windowHours := window.Hours()
	hourlyRate := 0.0
	if windowHours > 0 {
		hourlyRate = teamSpend / windowHours
	}
	dailyRate := hourlyRate * 24

	activation := map[string]interface{}{
		"team_spend":     teamSpend,
		"project_spend":  projectSpend,
		"resource_spend": 0.0,
		"hourly_rate":    hourlyRate,
		"daily_rate":     dailyRate,
		"threshold":      policy.ThresholdAmount,
		"team":           policy.Team,
		"project":        policy.Project,
		"resource_id":    "",
	}

	// Evaluate CEL expression
	e.compiledMu.RLock()
	prog, exists := e.compiledRules[policy.ID]
	e.compiledMu.RUnlock()

	if !exists {
		return nil // Policy not compiled (e.g., disabled or had error)
	}

	out, _, err := prog.Eval(activation)
	if err != nil {
		return fmt.Errorf("eval CEL: %w", err)
	}

	breached, ok := out.Value().(bool)
	if !ok {
		return fmt.Errorf("CEL expression did not return bool, got %T", out.Value())
	}

	if breached {
		event := models.BreachEvent{
			ID:          fmt.Sprintf("breach-%d", time.Now().UnixNano()),
			PolicyID:    policy.ID,
			ResourceID:  "team-level",
			Team:        policy.Team,
			Project:     policy.Project,
			Severity:    highestSeverity(policy.Actions),
			Threshold:   policy.ThresholdAmount,
			ActualValue: teamSpend,
			Message: fmt.Sprintf("Policy '%s' breached: team=%s spend=$%.2f exceeds threshold=$%.2f (window=%s)",
				policy.Name, policy.Team, teamSpend, policy.ThresholdAmount, policy.TimeWindow),
			Timestamp:    time.Now(),
			ActionsTaken: actionTypes(policy.Actions),
		}

		if err := e.breachHandler(event); err != nil {
			return fmt.Errorf("breach handler: %w", err)
		}
	}

	return nil
}

// Run starts the evaluation loop
func (e *CircuitBreakerEngine) Run(ctx context.Context) {
	ticker := time.NewTicker(e.evalInterval)
	defer ticker.Stop()

	log.Printf("Circuit breaker engine started (eval interval: %v)", e.evalInterval)

	for {
		select {
		case <-ctx.Done():
			log.Println("Circuit breaker engine stopped")
			return
		case <-ticker.C:
			if err := e.EvaluateAll(ctx); err != nil {
				log.Printf("ERROR: evaluation cycle: %v", err)
			}
		}
	}
}

// SetEvalInterval sets the evaluation interval (useful for testing)
func (e *CircuitBreakerEngine) SetEvalInterval(d time.Duration) {
	e.evalInterval = d
}

// parseTimeWindow converts a string window like "1h", "24h", "7d", "30d" to duration
func parseTimeWindow(window string) (time.Duration, error) {
	switch window {
	case "1h":
		return time.Hour, nil
	case "6h":
		return 6 * time.Hour, nil
	case "12h":
		return 12 * time.Hour, nil
	case "24h":
		return 24 * time.Hour, nil
	case "7d":
		return 7 * 24 * time.Hour, nil
	case "30d":
		return 30 * 24 * time.Hour, nil
	}

	// Try standard Go duration parsing
	d, err := time.ParseDuration(window)
	if err != nil {
		return 0, fmt.Errorf("unknown time window %q", window)
	}
	return d, nil
}

// highestSeverity returns the highest severity action type
func highestSeverity(actions []models.PolicyAction) string {
	order := map[string]int{
		"notify":    1,
		"throttle":  2,
		"halt":      3,
		"terminate": 4,
	}

	highest := "notify"
	for _, a := range actions {
		if order[a.Type] > order[highest] {
			highest = a.Type
		}
	}
	return highest
}

// actionTypes returns a list of action type strings
func actionTypes(actions []models.PolicyAction) []string {
	types := make([]string, len(actions))
	for i, a := range actions {
		types[i] = a.Type
	}
	return types
}