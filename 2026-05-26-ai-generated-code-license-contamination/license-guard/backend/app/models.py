import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, DateTime, ForeignKey,
    Integer, JSON, func
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


class CorpusSnippet(Base):
    __tablename__ = "corpus_snippets"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    source_repo = Column(String(500), nullable=False)
    source_file = Column(String(500), nullable=False)
    license_spdx = Column(String(100), nullable=False)
    license_risk_tier = Column(String(20), nullable=False)
    language = Column(String(50), nullable=True)
    code_snippet = Column(Text(), nullable=False)
    ast_tokens = Column(JSONB(), nullable=True)
    minhash_signature = Column(ARRAY(Integer()), nullable=True)
    if PGVECTOR_AVAILABLE:
        embedding = Column(Vector(384), nullable=True)
    else:
        embedding = Column(JSONB(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    status = Column(String(20), nullable=False, default='pending')
    source = Column(String(50), nullable=False)  # ai_assistant, pre_commit, ci_cd
    language = Column(String(50), nullable=True)
    filename = Column(String(500), nullable=True)
    code_snippet = Column(Text(), nullable=False)
    risk_tier = Column(String(20), nullable=True)
    result = Column(JSONB(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSONB(), nullable=True)

    matches = relationship("ScanMatch", back_populates="scan_job",
                           cascade="all, delete-orphan", lazy="select")
    remediations = relationship("RemediationSuggestion", back_populates="scan_job",
                                cascade="all, delete-orphan", lazy="select")


class ScanMatch(Base):
    __tablename__ = "scan_matches"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    scan_job_id = Column(String(36), ForeignKey('scan_jobs.id', ondelete='CASCADE'), nullable=False)
    corpus_snippet_id = Column(String(36), ForeignKey('corpus_snippets.id', ondelete='SET NULL'), nullable=True)
    match_type = Column(String(30), nullable=False)  # exact, near_duplicate, semantic
    similarity_score = Column(Float(), nullable=False)
    license_spdx = Column(String(100), nullable=False)
    license_risk_tier = Column(String(20), nullable=False)
    matched_snippet = Column(Text(), nullable=True)
    source_repo = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scan_job = relationship("ScanJob", back_populates="matches")
    remediations = relationship("RemediationSuggestion", back_populates="match")


class RemediationSuggestion(Base):
    __tablename__ = "remediation_suggestions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    scan_job_id = Column(String(36), ForeignKey('scan_jobs.id', ondelete='CASCADE'), nullable=False)
    match_id = Column(String(36), ForeignKey('scan_matches.id', ondelete='CASCADE'), nullable=True)
    original_code = Column(Text(), nullable=False)
    suggested_code = Column(Text(), nullable=True)
    explanation = Column(Text(), nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scan_job = relationship("ScanJob", back_populates="remediations")
    match = relationship("ScanMatch", back_populates="remediations")