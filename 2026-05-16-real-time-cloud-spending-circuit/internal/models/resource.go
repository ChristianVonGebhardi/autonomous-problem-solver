package models

import (
	"time"
)

// CloudProvider represents supported cloud providers
type CloudProvider string

const (
	AWS   CloudProvider = "aws"
	Azure CloudProvider = "azure"
	GCP   CloudProvider = "gcp"
)

// Resource represents a cloud resource being monitored
type Resource struct {
	ID           string        `json:"id"`
	Provider     CloudProvider `json:"provider"`
	Type         string        `json:"type"`
	Region       string        `json:"region"`
	Tags         map[string]string `json:"tags"`
	Team         string        `json:"team"`
	Project      string        `json:"project"`
	State        string        `json:"state"`
	CreatedAt    time.Time     `json:"created_at"`
	DiscoveredAt time.Time     `json:"discovered_at"`
}

// CostMetric represents a spending data point
type CostMetric struct {
	ResourceID    string        `json:"resource_id"`
	Provider      CloudProvider `json:"provider"`
	Team          string        `json:"team"`
	Project       string        `json:"project"`
	Timestamp     time.Time     `json:"timestamp"`
	Cost          float64       `json:"cost"`
	Currency      string        `json:"currency"`
	MetricType    string        `json:"metric_type"` // hourly, daily, cumulative
	ServiceName   string        `json:"service_name"`
}

// BreachEvent represents a policy violation
type BreachEvent struct {
	ID            string        `json:"id"`
	PolicyID      string        `json:"policy_id"`
	ResourceID    string        `json:"resource_id"`
	Team          string        `json:"team"`
	Project       string        `json:"project"`
	Severity      string        `json:"severity"` // warn, throttle, halt, terminate
	Threshold     float64       `json:"threshold"`
	ActualValue   float64       `json:"actual_value"`
	Message       string        `json:"message"`
	Timestamp     time.Time     `json:"timestamp"`
	ActionsTaken  []string      `json:"actions_taken"`
}

// Policy represents a spending circuit breaker rule
type Policy struct {
	ID              string            `json:"id" yaml:"id"`
	Name            string            `json:"name" yaml:"name"`
	Description     string            `json:"description" yaml:"description"`
	Team            string            `json:"team" yaml:"team"`
	Project         string            `json:"project" yaml:"project"`
	Enabled         bool              `json:"enabled" yaml:"enabled"`
	CELExpression   string            `json:"cel_expression" yaml:"cel_expression"`
	ThresholdAmount float64           `json:"threshold_amount" yaml:"threshold_amount"`
	TimeWindow      string            `json:"time_window" yaml:"time_window"` // 1h, 24h, 7d, 30d
	Actions         []PolicyAction    `json:"actions" yaml:"actions"`
	Metadata        map[string]string `json:"metadata" yaml:"metadata"`
}

// PolicyAction defines what happens when a policy breaches
type PolicyAction struct {
	Type       string            `json:"type" yaml:"type"` // notify, throttle, halt, terminate
	Severity   string            `json:"severity" yaml:"severity"`
	Parameters map[string]string `json:"parameters" yaml:"parameters"`
}