package policy

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"gopkg.in/yaml.v3"
)

// PolicyFile represents the YAML policy file format
type PolicyFile struct {
	Version  string          `yaml:"version"`
	Policies []PolicyDef     `yaml:"policies"`
}

// PolicyDef is the YAML definition of a policy
type PolicyDef struct {
	ID              string            `yaml:"id"`
	Name            string            `yaml:"name"`
	Description     string            `yaml:"description"`
	Team            string            `yaml:"team"`
	Project         string            `yaml:"project"`
	Enabled         bool              `yaml:"enabled"`
	CELExpression   string            `yaml:"cel_expression"`
	ThresholdAmount float64           `yaml:"threshold_amount"`
	TimeWindow      string            `yaml:"time_window"`
	Actions         []ActionDef       `yaml:"actions"`
	Metadata        map[string]string `yaml:"metadata"`
}

// ActionDef is the YAML definition of an action
type ActionDef struct {
	Type       string            `yaml:"type"`
	Severity   string            `yaml:"severity"`
	Parameters map[string]string `yaml:"parameters"`
}

// LoadFromFile loads policies from a YAML file
func LoadFromFile(path string) ([]models.Policy, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read file %s: %w", path, err)
	}

	return ParseYAML(data)
}

// ParseYAML parses policies from YAML bytes
func ParseYAML(data []byte) ([]models.Policy, error) {
	var pf PolicyFile
	if err := yaml.Unmarshal(data, &pf); err != nil {
		return nil, fmt.Errorf("parse yaml: %w", err)
	}

	var policies []models.Policy
	for _, def := range pf.Policies {
		p := models.Policy{
			ID:              def.ID,
			Name:            def.Name,
			Description:     def.Description,
			Team:            def.Team,
			Project:         def.Project,
			Enabled:         def.Enabled,
			CELExpression:   def.CELExpression,
			ThresholdAmount: def.ThresholdAmount,
			TimeWindow:      def.TimeWindow,
			Metadata:        def.Metadata,
		}

		for _, a := range def.Actions {
			p.Actions = append(p.Actions, models.PolicyAction{
				Type:       a.Type,
				Severity:   a.Severity,
				Parameters: a.Parameters,
			})
		}

		policies = append(policies, p)
	}

	return policies, nil
}

// LoadFromDirectory loads all .yaml and .yml policy files from a directory
func LoadFromDirectory(dir string) ([]models.Policy, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read directory %s: %w", dir, err)
	}

	var all []models.Policy
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		name := entry.Name()
		if !strings.HasSuffix(name, ".yaml") && !strings.HasSuffix(name, ".yml") {
			continue
		}

		path := filepath.Join(dir, name)
		policies, err := LoadFromFile(path)
		if err != nil {
			return nil, fmt.Errorf("load %s: %w", path, err)
		}

		all = append(all, policies...)
	}

	return all, nil
}

// Validate checks a policy for common errors
func Validate(p models.Policy) []string {
	var errors []string

	if p.ID == "" {
		errors = append(errors, "id is required")
	}
	if p.Name == "" {
		errors = append(errors, "name is required")
	}
	if p.Team == "" {
		errors = append(errors, "team is required")
	}
	if p.CELExpression == "" {
		errors = append(errors, "cel_expression is required")
	}
	if p.ThresholdAmount <= 0 {
		errors = append(errors, "threshold_amount must be positive")
	}

	validWindows := map[string]bool{
		"1h": true, "6h": true, "12h": true,
		"24h": true, "7d": true, "30d": true,
	}
	if !validWindows[p.TimeWindow] {
		errors = append(errors, fmt.Sprintf("time_window %q is not valid (use: 1h, 6h, 12h, 24h, 7d, 30d)", p.TimeWindow))
	}

	validActions := map[string]bool{
		"notify": true, "throttle": true, "halt": true, "terminate": true,
	}
	for i, a := range p.Actions {
		if !validActions[a.Type] {
			errors = append(errors, fmt.Sprintf("action[%d] type %q is invalid (use: notify, throttle, halt, terminate)", i, a.Type))
		}
	}

	return errors
}