package engine

import (
	"context"
	"testing"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
)

// mockFetcher implements SpendingFetcher for testing
type mockFetcher struct {
	teamSpend     float64
	projectSpend  float64
	resourceSpend float64
}

func (m *mockFetcher) GetTeamSpending(_ context.Context, _ string, _ time.Time) (float64, error) {
	return m.teamSpend, nil
}

func (m *mockFetcher) GetProjectSpending(_ context.Context, _, _ string, _ time.Time) (float64, error) {
	return m.projectSpend, nil
}

func (m *mockFetcher) GetResourceSpending(_ context.Context, _ string, _ time.Time) (float64, error) {
	return m.resourceSpend, nil
}

func TestCircuitBreakerEvaluation(t *testing.T) {
	fetcher := &mockFetcher{
		teamSpend:    150.0,
		projectSpend: 80.0,
	}

	var capturedEvent *models.BreachEvent
	handler := func(event models.BreachEvent) error {
		capturedEvent = &event
		return nil
	}

	eng, err := NewCircuitBreakerEngine(fetcher, handler)
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}

	policies := []models.Policy{
		{
			ID:              "test-policy-1",
			Name:            "Team spend limit",
			Team:            "platform",
			Project:         "api",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 100.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
			},
		},
	}

	if err := eng.LoadPolicies(policies); err != nil {
		t.Fatalf("load policies: %v", err)
	}

	ctx := context.Background()
	if err := eng.EvaluateAll(ctx); err != nil {
		t.Fatalf("evaluate: %v", err)
	}

	if capturedEvent == nil {
		t.Fatal("expected breach event to be fired")
	}

	if capturedEvent.PolicyID != "test-policy-1" {
		t.Errorf("expected policy ID test-policy-1, got %s", capturedEvent.PolicyID)
	}

	if capturedEvent.ActualValue != 150.0 {
		t.Errorf("expected actual value 150.0, got %f", capturedEvent.ActualValue)
	}
}

func TestCircuitBreakerNoBreachBelowThreshold(t *testing.T) {
	fetcher := &mockFetcher{
		teamSpend: 50.0,
	}

	var capturedEvent *models.BreachEvent
	handler := func(event models.BreachEvent) error {
		capturedEvent = &event
		return nil
	}

	eng, err := NewCircuitBreakerEngine(fetcher, handler)
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}

	policies := []models.Policy{
		{
			ID:              "test-policy-2",
			Name:            "Team spend limit",
			Team:            "platform",
			Project:         "api",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 100.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
			},
		},
	}

	if err := eng.LoadPolicies(policies); err != nil {
		t.Fatalf("load policies: %v", err)
	}

	ctx := context.Background()
	if err := eng.EvaluateAll(ctx); err != nil {
		t.Fatalf("evaluate: %v", err)
	}

	if capturedEvent != nil {
		t.Errorf("expected no breach, but got event: %+v", capturedEvent)
	}
}

func TestParseTimeWindow(t *testing.T) {
	cases := []struct {
		input    string
		expected time.Duration
		wantErr  bool
	}{
		{"1h", time.Hour, false},
		{"24h", 24 * time.Hour, false},
		{"7d", 7 * 24 * time.Hour, false},
		{"30d", 30 * 24 * time.Hour, false},
		{"invalid", 0, true},
	}

	for _, tc := range cases {
		d, err := parseTimeWindow(tc.input)
		if tc.wantErr {
			if err == nil {
				t.Errorf("expected error for %q", tc.input)
			}
			continue
		}
		if err != nil {
			t.Errorf("unexpected error for %q: %v", tc.input, err)
			continue
		}
		if d != tc.expected {
			t.Errorf("for %q: expected %v, got %v", tc.input, tc.expected, d)
		}
	}
}

func TestCELComplexExpression(t *testing.T) {
	fetcher := &mockFetcher{
		teamSpend:    500.0,
		projectSpend: 200.0,
	}

	var breachCount int
	handler := func(event models.BreachEvent) error {
		breachCount++
		return nil
	}

	eng, err := NewCircuitBreakerEngine(fetcher, handler)
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}

	policies := []models.Policy{
		{
			ID:              "complex-policy",
			Name:            "Complex rule",
			Team:            "data",
			Project:         "ml",
			Enabled:         true,
			CELExpression:   "team_spend > threshold && daily_rate > 20.0",
			ThresholdAmount: 100.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "halt", Severity: "critical"},
			},
		},
	}

	if err := eng.LoadPolicies(policies); err != nil {
		t.Fatalf("load policies: %v", err)
	}

	ctx := context.Background()
	if err := eng.EvaluateAll(ctx); err != nil {
		t.Fatalf("evaluate: %v", err)
	}

	if breachCount != 1 {
		t.Errorf("expected 1 breach, got %d", breachCount)
	}
}

func TestDisabledPolicySkipped(t *testing.T) {
	fetcher := &mockFetcher{teamSpend: 999.0}

	var breachCount int
	handler := func(event models.BreachEvent) error {
		breachCount++
		return nil
	}

	eng, err := NewCircuitBreakerEngine(fetcher, handler)
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}

	policies := []models.Policy{
		{
			ID:              "disabled-policy",
			Name:            "Disabled",
			Team:            "platform",
			Project:         "api",
			Enabled:         false, // disabled
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 1.0,
			TimeWindow:      "24h",
			Actions:         []models.PolicyAction{{Type: "notify"}},
		},
	}

	if err := eng.LoadPolicies(policies); err != nil {
		t.Fatalf("load policies: %v", err)
	}

	ctx := context.Background()
	if err := eng.EvaluateAll(ctx); err != nil {
		t.Fatalf("evaluate: %v", err)
	}

	if breachCount != 0 {
		t.Errorf("expected 0 breaches for disabled policy, got %d", breachCount)
	}
}