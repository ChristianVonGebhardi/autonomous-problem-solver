"""Initialize database schema and TimescaleDB hypertables."""
import asyncio
import psycopg2
from psycopg2.extras import execute_values
import re

from app.config import settings


def get_sync_url(url: str) -> str:
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres+asyncpg://", "postgresql://")
    return url


def init_database():
    sync_url = get_sync_url(settings.database_url)
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Try to create TimescaleDB extension (may not be available in plain postgres)
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
        print("✓ TimescaleDB extension enabled")
    except Exception as e:
        print(f"  TimescaleDB not available (using plain postgres): {e}")
        conn.rollback()
        conn = psycopg2.connect(sync_url)
        conn.autocommit = True
        cur = conn.cursor()

    # Create tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS repositories (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255) UNIQUE NOT NULL,
            ci_system VARCHAR(50) DEFAULT 'unknown',
            default_branch VARCHAR(100) DEFAULT 'main',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_runs (
            id SERIAL PRIMARY KEY,
            repo_id INTEGER REFERENCES repositories(id),
            test_name VARCHAR(500) NOT NULL,
            test_file VARCHAR(500),
            test_class VARCHAR(255),
            branch VARCHAR(255),
            commit_sha VARCHAR(64),
            pipeline_id VARCHAR(255),
            status VARCHAR(50) NOT NULL,
            duration_ms INTEGER,
            log_output TEXT,
            error_message TEXT,
            stack_trace TEXT,
            ci_system VARCHAR(50) DEFAULT 'unknown',
            environment_vars JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Try to create hypertable for time-series
    try:
        cur.execute("""
            SELECT create_hypertable('test_runs', 'created_at', 
                                     if_not_exists => TRUE,
                                     migrate_data => TRUE);
        """)
        print("✓ test_runs hypertable created")
    except Exception as e:
        print(f"  Hypertable not created (using plain table): {e}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS flaky_tests (
            id SERIAL PRIMARY KEY,
            repo_id INTEGER REFERENCES repositories(id),
            test_name VARCHAR(500) NOT NULL,
            test_file VARCHAR(500),
            flakiness_score FLOAT NOT NULL,
            total_runs INTEGER DEFAULT 0,
            failed_runs INTEGER DEFAULT 0,
            pass_rate FLOAT,
            is_active BOOLEAN DEFAULT TRUE,
            first_detected_at TIMESTAMPTZ DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ,
            last_analyzed_at TIMESTAMPTZ,
            UNIQUE(repo_id, test_name)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS root_cause_analyses (
            id SERIAL PRIMARY KEY,
            flaky_test_id INTEGER REFERENCES flaky_tests(id),
            primary_cause VARCHAR(50) NOT NULL,
            confidence FLOAT NOT NULL,
            secondary_causes JSONB,
            evidence JSONB,
            classifier_version VARCHAR(50) DEFAULT 'rule_based_v1',
            model_scores JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fix_proposals (
            id SERIAL PRIMARY KEY,
            flaky_test_id INTEGER REFERENCES flaky_tests(id),
            status VARCHAR(50) DEFAULT 'pending',
            root_cause VARCHAR(50),
            patch_diff TEXT,
            explanation TEXT,
            affected_files JSONB,
            confidence FLOAT,
            pr_url VARCHAR(500),
            pr_number INTEGER,
            feedback_accepted BOOLEAN,
            feedback_note TEXT,
            llm_model VARCHAR(100),
            context_used TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        );
    """)

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_repo_test ON test_runs(repo_id, test_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_created ON test_runs(created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flaky_tests_score ON flaky_tests(flakiness_score);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flaky_tests_repo ON flaky_tests(repo_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fix_proposals_status ON fix_proposals(status);")

    cur.close()
    conn.close()
    print("✓ Database schema initialized")


if __name__ == "__main__":
    init_database()