-- TimescaleDB schema for cloud spending circuit breaker

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Resources table
CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    type TEXT NOT NULL,
    region TEXT NOT NULL,
    tags JSONB,
    team TEXT NOT NULL,
    project TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resources_team_project ON resources(team, project);
CREATE INDEX IF NOT EXISTS idx_resources_provider ON resources(provider);
CREATE INDEX IF NOT EXISTS idx_resources_tags ON resources USING GIN(tags);

-- Cost metrics table (hypertable)
CREATE TABLE IF NOT EXISTS cost_metrics (
    time TIMESTAMPTZ NOT NULL,
    resource_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    team TEXT NOT NULL,
    project TEXT NOT NULL,
    cost DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    metric_type TEXT NOT NULL,
    service_name TEXT NOT NULL,
    tags JSONB
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable('cost_metrics', 'time', if_not_exists => TRUE);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_cost_metrics_resource ON cost_metrics(resource_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_cost_metrics_team_project ON cost_metrics(team, project, time DESC);
CREATE INDEX IF NOT EXISTS idx_cost_metrics_provider ON cost_metrics(provider, time DESC);

-- Continuous aggregate for hourly rollups
CREATE MATERIALIZED VIEW IF NOT EXISTS cost_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    resource_id,
    provider,
    team,
    project,
    service_name,
    SUM(cost) AS total_cost,
    AVG(cost) AS avg_cost,
    MAX(cost) AS max_cost,
    COUNT(*) AS data_points
FROM cost_metrics
GROUP BY bucket, resource_id, provider, team, project, service_name;

-- Continuous aggregate for daily rollups
CREATE MATERIALIZED VIEW IF NOT EXISTS cost_metrics_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    provider,
    team,
    project,
    service_name,
    SUM(cost) AS total_cost,
    AVG(cost) AS avg_cost,
    MAX(cost) AS max_cost,
    COUNT(DISTINCT resource_id) AS resource_count
FROM cost_metrics
GROUP BY bucket, provider, team, project, service_name;

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    team TEXT NOT NULL,
    project TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    cel_expression TEXT NOT NULL,
    threshold_amount DOUBLE PRECISION NOT NULL,
    time_window TEXT NOT NULL,
    actions JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policies_team_project ON policies(team, project);
CREATE INDEX IF NOT EXISTS idx_policies_enabled ON policies(enabled);

-- Breach events table (hypertable)
CREATE TABLE IF NOT EXISTS breach_events (
    time TIMESTAMPTZ NOT NULL,
    id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    team TEXT NOT NULL,
    project TEXT NOT NULL,
    severity TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    actual_value DOUBLE PRECISION NOT NULL,
    message TEXT NOT NULL,
    actions_taken JSONB,
    metadata JSONB
);

SELECT create_hypertable('breach_events', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_breach_events_policy ON breach_events(policy_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_breach_events_team ON breach_events(team, time DESC);
CREATE INDEX IF NOT EXISTS idx_breach_events_severity ON breach_events(severity, time DESC);

-- Add refresh policies for continuous aggregates
SELECT add_continuous_aggregate_policy('cost_metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('cost_metrics_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Retention policy: keep raw metrics for 90 days
SELECT add_retention_policy('cost_metrics', INTERVAL '90 days', if_not_exists => TRUE);

-- Retention policy: keep breach events for 1 year
SELECT add_retention_policy('breach_events', INTERVAL '365 days', if_not_exists => TRUE);