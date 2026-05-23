package database

import (
	"context"
	"fmt"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Database struct {
	pool *pgxpool.Pool
}

func NewDatabase(connString string) (*Database, error) {
	config, err := pgxpool.ParseConfig(connString)
	if err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	config.MaxConns = 25
	config.MinConns = 5
	config.MaxConnLifetime = time.Hour
	config.MaxConnIdleTime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		return nil, fmt.Errorf("create pool: %w", err)
	}

	if err := pool.Ping(context.Background()); err != nil {
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return &Database{pool: pool}, nil
}

func (db *Database) Close() {
	db.pool.Close()
}

// UpsertResource inserts or updates a resource
func (db *Database) UpsertResource(ctx context.Context, resource *models.Resource) error {
	query := `
		INSERT INTO resources (id, provider, type, region, tags, team, project, state, created_at, discovered_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
		ON CONFLICT (id) DO UPDATE SET
			type = EXCLUDED.type,
			region = EXCLUDED.region,
			tags = EXCLUDED.tags,
			team = EXCLUDED.team,
			project = EXCLUDED.project,
			state = EXCLUDED.state,
			updated_at = NOW()
	`

	_, err := db.pool.Exec(ctx, query,
		resource.ID,
		resource.Provider,
		resource.Type,
		resource.Region,
		resource.Tags,
		resource.Team,
		resource.Project,
		resource.State,
		resource.CreatedAt,
		resource.DiscoveredAt,
	)

	return err
}

// InsertCostMetric inserts a cost metric
func (db *Database) InsertCostMetric(ctx context.Context, metric *models.CostMetric) error {
	query := `
		INSERT INTO cost_metrics (time, resource_id, provider, team, project, cost, currency, metric_type, service_name, tags)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`

	_, err := db.pool.Exec(ctx, query,
		metric.Timestamp,
		metric.ResourceID,
		metric.Provider,
		metric.Team,
		metric.Project,
		metric.Cost,
		metric.Currency,
		metric.MetricType,
		metric.ServiceName,
		nil, // tags
	)

	return err
}

// InsertCostMetricsBatch inserts multiple cost metrics efficiently
func (db *Database) InsertCostMetricsBatch(ctx context.Context, metrics []models.CostMetric) error {
	if len(metrics) == 0 {
		return nil
	}

	batch := &pgx.Batch{}
	query := `
		INSERT INTO cost_metrics (time, resource_id, provider, team, project, cost, currency, metric_type, service_name)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	`

	for _, m := range metrics {
		batch.Queue(query, m.Timestamp, m.ResourceID, m.Provider, m.Team, m.Project, m.Cost, m.Currency, m.MetricType, m.ServiceName)
	}

	br := db.pool.SendBatch(ctx, batch)
	defer br.Close()

	for range metrics {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("batch insert: %w", err)
		}
	}

	return nil
}

// GetTeamSpending returns total spending for a team within a time window
func (db *Database) GetTeamSpending(ctx context.Context, team string, since time.Time) (float64, error) {
	query := `
		SELECT COALESCE(SUM(cost), 0) as total
		FROM cost_metrics
		WHERE team = $1 AND time >= $2
	`

	var total float64
	err := db.pool.QueryRow(ctx, query, team, since).Scan(&total)
	return total, err
}

// GetResourceSpending returns spending for a specific resource within a time window
func (db *Database) GetResourceSpending(ctx context.Context, resourceID string, since time.Time) (float64, error) {
	query := `
		SELECT COALESCE(SUM(cost), 0) as total
		FROM cost_metrics
		WHERE resource_id = $1 AND time >= $2
	`

	var total float64
	err := db.pool.QueryRow(ctx, query, resourceID, since).Scan(&total)
	return total, err
}

// GetProjectSpending returns spending for a project within a time window
func (db *Database) GetProjectSpending(ctx context.Context, team, project string, since time.Time) (float64, error) {
	query := `
		SELECT COALESCE(SUM(cost), 0) as total
		FROM cost_metrics
		WHERE team = $1 AND project = $2 AND time >= $3
	`

	var total float64
	err := db.pool.QueryRow(ctx, query, team, project, since).Scan(&total)
	return total, err
}

// UpsertPolicy inserts or updates a policy
func (db *Database) UpsertPolicy(ctx context.Context, policy *models.Policy) error {
	query := `
		INSERT INTO policies (id, name, description, team, project, enabled, cel_expression, threshold_amount, time_window, actions, metadata, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
		ON CONFLICT (id) DO UPDATE SET
			name = EXCLUDED.name,
			description = EXCLUDED.description,
			enabled = EXCLUDED.enabled,
			cel_expression = EXCLUDED.cel_expression,
			threshold_amount = EXCLUDED.threshold_amount,
			time_window = EXCLUDED.time_window,
			actions = EXCLUDED.actions,
			metadata = EXCLUDED.metadata,
			updated_at = NOW()
	`

	_, err := db.pool.Exec(ctx, query,
		policy.ID,
		policy.Name,
		policy.Description,
		policy.Team,
		policy.Project,
		policy.Enabled,
		policy.CELExpression,
		policy.ThresholdAmount,
		policy.TimeWindow,
		policy.Actions,
		policy.Metadata,
	)

	return err
}

// GetActivePolicies returns all enabled policies
func (db *Database) GetActivePolicies(ctx context.Context) ([]models.Policy, error) {
	query := `
		SELECT id, name, description, team, project, enabled, cel_expression, threshold_amount, time_window, actions, metadata
		FROM policies
		WHERE enabled = true
		ORDER BY team, project, name
	`

	rows, err := db.pool.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var policies []models.Policy
	for rows.Next() {
		var p models.Policy
		var actionsJSON []byte
		var metadataJSON []byte

		err := rows.Scan(&p.ID, &p.Name, &p.Description, &p.Team, &p.Project, &p.Enabled,
			&p.CELExpression, &p.ThresholdAmount, &p.TimeWindow, &actionsJSON, &metadataJSON)
		if err != nil {
			return nil, err
		}

		policies = append(policies, p)
	}

	return policies, rows.Err()
}

// InsertBreachEvent inserts a breach event
func (db *Database) InsertBreachEvent(ctx context.Context, event *models.BreachEvent) error {
	query := `
		INSERT INTO breach_events (time, id, policy_id, resource_id, team, project, severity, threshold, actual_value, message, actions_taken)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
	`

	_, err := db.pool.Exec(ctx, query,
		event.Timestamp,
		event.ID,
		event.PolicyID,
		event.ResourceID,
		event.Team,
		event.Project,
		event.Severity,
		event.Threshold,
		event.ActualValue,
		event.Message,
		event.ActionsTaken,
	)

	return err
}

// GetRecentBreaches returns recent breach events
func (db *Database) GetRecentBreaches(ctx context.Context, limit int) ([]models.BreachEvent, error) {
	query := `
		SELECT time, id, policy_id, resource_id, team, project, severity, threshold, actual_value, message, actions_taken
		FROM breach_events
		ORDER BY time DESC
		LIMIT $1
	`

	rows, err := db.pool.Query(ctx, query, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []models.BreachEvent
	for rows.Next() {
		var e models.BreachEvent
		var actionsJSON []byte

		err := rows.Scan(&e.Timestamp, &e.ID, &e.PolicyID, &e.ResourceID, &e.Team, &e.Project,
			&e.Severity, &e.Threshold, &e.ActualValue, &e.Message, &actionsJSON)
		if err != nil {
			return nil, err
		}

		events = append(events, e)
	}

	return events, rows.Err()
}