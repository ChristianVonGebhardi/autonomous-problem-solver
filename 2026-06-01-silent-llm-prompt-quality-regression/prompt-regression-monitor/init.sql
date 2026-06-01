CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Prompt template registry
CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    system_prompt_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Golden reference examples
CREATE TABLE IF NOT EXISTS golden_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(id) ON DELETE CASCADE,
    input_messages JSONB NOT NULL,
    expected_output TEXT NOT NULL,
    output_embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Production inference logs
CREATE TABLE IF NOT EXISTS inference_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(id),
    template_name VARCHAR(255),
    request_payload JSONB NOT NULL,
    response_payload JSONB,
    model VARCHAR(255),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms FLOAT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Quality scores per inference
CREATE TABLE IF NOT EXISTS quality_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inference_log_id UUID REFERENCES inference_logs(id) ON DELETE CASCADE,
    template_id UUID REFERENCES prompt_templates(id),
    metric_name VARCHAR(100) NOT NULL,
    score FLOAT NOT NULL,
    metadata JSONB DEFAULT '{}',
    scored_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quality_scores_template_metric 
    ON quality_scores(template_id, metric_name, scored_at);
CREATE INDEX IF NOT EXISTS idx_quality_scores_inference 
    ON quality_scores(inference_log_id);
CREATE INDEX IF NOT EXISTS idx_inference_logs_template 
    ON inference_logs(template_id, created_at);
CREATE INDEX IF NOT EXISTS idx_golden_references_template 
    ON golden_references(template_id);

-- Drift alerts
CREATE TABLE IF NOT EXISTS drift_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(id),
    template_name VARCHAR(255),
    metric_name VARCHAR(100) NOT NULL,
    detector_type VARCHAR(50) NOT NULL,
    severity VARCHAR(50) DEFAULT 'warning',
    baseline_mean FLOAT,
    current_mean FLOAT,
    p_value FLOAT,
    cusum_stat FLOAT,
    evidence JSONB DEFAULT '{}',
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drift_alerts_template 
    ON drift_alerts(template_id, created_at);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_unacked 
    ON drift_alerts(acknowledged, created_at);

-- Metric time-series aggregates (hourly)
CREATE TABLE IF NOT EXISTS metric_aggregates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(id),
    metric_name VARCHAR(100) NOT NULL,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    sample_count INTEGER NOT NULL,
    mean_score FLOAT NOT NULL,
    std_score FLOAT,
    min_score FLOAT,
    max_score FLOAT,
    p10_score FLOAT,
    p50_score FLOAT,
    p90_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_metric_aggregates_unique 
    ON metric_aggregates(template_id, metric_name, window_start);

-- Insert default template
INSERT INTO prompt_templates (name, description) 
VALUES ('default', 'Default template for untagged requests')
ON CONFLICT (name) DO NOTHING;