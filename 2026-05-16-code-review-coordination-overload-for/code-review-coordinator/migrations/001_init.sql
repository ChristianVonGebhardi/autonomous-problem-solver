-- Core schema for Code Review Coordinator

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Reviewers / team members
CREATE TABLE reviewers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    slack_user_id VARCHAR(255),
    timezone VARCHAR(100) DEFAULT 'UTC',
    max_concurrent_reviews INT DEFAULT 3,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Expertise areas per reviewer
CREATE TABLE reviewer_expertise (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reviewer_id UUID REFERENCES reviewers(id) ON DELETE CASCADE,
    file_pattern VARCHAR(500) NOT NULL,  -- e.g. "*.go", "frontend/**", "services/auth/**"
    expertise_level INT DEFAULT 5,       -- 1-10 scale
    pr_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pull requests
CREATE TABLE pull_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255) NOT NULL,   -- GitHub/GitLab PR number
    repo_full_name VARCHAR(500) NOT NULL,
    title VARCHAR(1000) NOT NULL,
    description TEXT,
    author_username VARCHAR(255) NOT NULL,
    vcs_type VARCHAR(50) DEFAULT 'github',  -- github, gitlab, bitbucket
    pr_url VARCHAR(1000),
    base_branch VARCHAR(255) DEFAULT 'main',
    head_branch VARCHAR(255),
    state VARCHAR(50) DEFAULT 'open',    -- open, assigned, in_review, merged, closed
    lines_added INT DEFAULT 0,
    lines_deleted INT DEFAULT 0,
    files_changed INT DEFAULT 0,
    complexity_score FLOAT,
    risk_score FLOAT,
    estimated_review_minutes INT,
    priority INT DEFAULT 5,              -- 1-10, higher = more urgent
    labels TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    vcs_created_at TIMESTAMPTZ,
    UNIQUE(external_id, repo_full_name)
);

-- Review assignments
CREATE TABLE review_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pr_id UUID REFERENCES pull_requests(id) ON DELETE CASCADE,
    reviewer_id UUID REFERENCES reviewers(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    pickup_at TIMESTAMPTZ,               -- when reviewer started
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, completed, reassigned
    routing_reason TEXT,                  -- explanation of why this reviewer was chosen
    score FLOAT,                          -- routing score used
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reviewer capacity snapshots (time-series)
CREATE TABLE capacity_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reviewer_id UUID REFERENCES reviewers(id) ON DELETE CASCADE,
    active_reviews INT DEFAULT 0,
    pending_reviews INT DEFAULT 0,
    capacity_score FLOAT DEFAULT 1.0,    -- 0.0 = fully booked, 1.0 = fully available
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- PR analysis metrics (detailed breakdown)
CREATE TABLE pr_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pr_id UUID REFERENCES pull_requests(id) ON DELETE CASCADE,
    metric_name VARCHAR(255) NOT NULL,
    metric_value FLOAT NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Notification log
CREATE TABLE notification_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assignment_id UUID REFERENCES review_assignments(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL,        -- slack, email, teams
    recipient VARCHAR(255) NOT NULL,
    message_preview TEXT,
    status VARCHAR(50) DEFAULT 'sent',   -- sent, failed, acknowledged
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook events log (for debugging/audit)
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,         -- github, gitlab, bitbucket
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_prs_state ON pull_requests(state);
CREATE INDEX idx_prs_author ON pull_requests(author_username);
CREATE INDEX idx_prs_created ON pull_requests(created_at DESC);
CREATE INDEX idx_assignments_reviewer ON review_assignments(reviewer_id);
CREATE INDEX idx_assignments_pr ON review_assignments(pr_id);
CREATE INDEX idx_assignments_status ON review_assignments(status);
CREATE INDEX idx_capacity_reviewer_time ON capacity_snapshots(reviewer_id, recorded_at DESC);
CREATE INDEX idx_webhook_events_processed ON webhook_events(processed, received_at);

-- Seed some test reviewers
INSERT INTO reviewers (username, display_name, email, slack_user_id, timezone, max_concurrent_reviews) VALUES
    ('alice_dev', 'Alice Chen', 'alice@example.com', 'U001ALICE', 'America/New_York', 4),
    ('bob_eng', 'Bob Smith', 'bob@example.com', 'U002BOB', 'America/Los_Angeles', 3),
    ('carol_sre', 'Carol Johnson', 'carol@example.com', 'U003CAROL', 'Europe/London', 3),
    ('david_ml', 'David Kim', 'david@example.com', 'U004DAVID', 'Asia/Seoul', 2),
    ('eve_sec', 'Eve Martinez', 'eve@example.com', 'U005EVE', 'America/Chicago', 3);

-- Seed expertise areas
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, '*.go', 9, 145 FROM reviewers r WHERE r.username = 'alice_dev';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, 'services/**', 8, 120 FROM reviewers r WHERE r.username = 'alice_dev';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, '*.ts', 7, 89 FROM reviewers r WHERE r.username = 'bob_eng';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, 'frontend/**', 9, 203 FROM reviewers r WHERE r.username = 'bob_eng';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, 'k8s/**', 10, 78 FROM reviewers r WHERE r.username = 'carol_sre';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, '*.yaml', 9, 156 FROM reviewers r WHERE r.username = 'carol_sre';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, '*.py', 10, 234 FROM reviewers r WHERE r.username = 'david_ml';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, 'ml/**', 10, 198 FROM reviewers r WHERE r.username = 'david_ml';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, 'auth/**', 10, 167 FROM reviewers r WHERE r.username = 'eve_sec';
INSERT INTO reviewer_expertise (reviewer_id, file_pattern, expertise_level, pr_count)
SELECT r.id, '*.security', 9, 145 FROM reviewers r WHERE r.username = 'eve_sec';