"""Initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create corpus_snippets table
    op.create_table(
        'corpus_snippets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_repo', sa.String(500), nullable=False),
        sa.Column('source_file', sa.String(500), nullable=False),
        sa.Column('license_spdx', sa.String(100), nullable=False),
        sa.Column('license_risk_tier', sa.String(20), nullable=False),
        sa.Column('language', sa.String(50), nullable=True),
        sa.Column('code_snippet', sa.Text(), nullable=False),
        sa.Column('ast_tokens', postgresql.JSONB(), nullable=True),
        sa.Column('minhash_signature', postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    # Create scan_jobs table
    op.create_table(
        'scan_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('source', sa.String(50), nullable=False),  # ai_assistant, pre_commit, ci_cd
        sa.Column('language', sa.String(50), nullable=True),
        sa.Column('filename', sa.String(500), nullable=True),
        sa.Column('code_snippet', sa.Text(), nullable=False),
        sa.Column('risk_tier', sa.String(20), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
    )
    
    # Create scan_matches table
    op.create_table(
        'scan_matches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('scan_job_id', sa.String(36), sa.ForeignKey('scan_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('corpus_snippet_id', sa.String(36), sa.ForeignKey('corpus_snippets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('match_type', sa.String(30), nullable=False),  # exact, near_duplicate, semantic
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('license_spdx', sa.String(100), nullable=False),
        sa.Column('license_risk_tier', sa.String(20), nullable=False),
        sa.Column('matched_snippet', sa.Text(), nullable=True),
        sa.Column('source_repo', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    # Create remediation_suggestions table
    op.create_table(
        'remediation_suggestions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('scan_job_id', sa.String(36), sa.ForeignKey('scan_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('match_id', sa.String(36), sa.ForeignKey('scan_matches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('original_code', sa.Text(), nullable=False),
        sa.Column('suggested_code', sa.Text(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    # Create indexes
    op.create_index('idx_scan_jobs_status', 'scan_jobs', ['status'])
    op.create_index('idx_scan_jobs_created_at', 'scan_jobs', ['created_at'])
    op.create_index('idx_scan_matches_scan_job_id', 'scan_matches', ['scan_job_id'])
    op.create_index('idx_corpus_language', 'corpus_snippets', ['language'])
    op.create_index('idx_corpus_license', 'corpus_snippets', ['license_spdx'])


def downgrade() -> None:
    op.drop_table('remediation_suggestions')
    op.drop_table('scan_matches')
    op.drop_table('scan_jobs')
    op.drop_table('corpus_snippets')
    op.execute('DROP EXTENSION IF EXISTS vector')