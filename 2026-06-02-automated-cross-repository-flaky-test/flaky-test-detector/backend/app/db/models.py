from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, JSON, Enum as SAEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class CISystem(str, enum.Enum):
    github_actions = "github_actions"
    gitlab_ci = "gitlab_ci"
    jenkins = "jenkins"
    circleci = "circleci"
    unknown = "unknown"


class TestStatus(str, enum.Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    error = "error"


class FlakinessCause(str, enum.Enum):
    timing = "timing"
    concurrency = "concurrency"
    environment = "environment"
    state_leakage = "state_leakage"
    unknown = "unknown"


class FixStatus(str, enum.Enum):
    pending = "pending"
    synthesizing = "synthesizing"
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    applied = "applied"


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), unique=True, nullable=False, index=True)
    ci_system = Column(SAEnum(CISystem), default=CISystem.unknown)
    default_branch = Column(String(100), default="main")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    test_runs = relationship("TestRun", back_populates="repository")
    flaky_tests = relationship("FlakyTest", back_populates="repository")


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    test_name = Column(String(500), nullable=False, index=True)
    test_file = Column(String(500))
    test_class = Column(String(255))
    branch = Column(String(255))
    commit_sha = Column(String(64))
    pipeline_id = Column(String(255))
    status = Column(SAEnum(TestStatus), nullable=False)
    duration_ms = Column(Integer)
    log_output = Column(Text)
    error_message = Column(Text)
    stack_trace = Column(Text)
    ci_system = Column(SAEnum(CISystem), default=CISystem.unknown)
    environment_vars = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    repository = relationship("Repository", back_populates="test_runs")

    __table_args__ = (
        Index("idx_test_runs_repo_test", "repo_id", "test_name"),
        Index("idx_test_runs_created", "created_at"),
    )


class FlakyTest(Base):
    __tablename__ = "flaky_tests"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    test_name = Column(String(500), nullable=False)
    test_file = Column(String(500))
    flakiness_score = Column(Float, nullable=False)
    total_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)
    pass_rate = Column(Float)
    is_active = Column(Boolean, default=True)
    first_detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True))
    last_analyzed_at = Column(DateTime(timezone=True))

    repository = relationship("Repository", back_populates="flaky_tests")
    analyses = relationship("RootCauseAnalysis", back_populates="flaky_test")
    fixes = relationship("FixProposal", back_populates="flaky_test")

    __table_args__ = (
        UniqueConstraint("repo_id", "test_name", name="uq_flaky_test_repo_name"),
        Index("idx_flaky_tests_score", "flakiness_score"),
    )


class RootCauseAnalysis(Base):
    __tablename__ = "root_cause_analyses"

    id = Column(Integer, primary_key=True, index=True)
    flaky_test_id = Column(Integer, ForeignKey("flaky_tests.id"), nullable=False)
    primary_cause = Column(SAEnum(FlakinessCause), nullable=False)
    confidence = Column(Float, nullable=False)
    secondary_causes = Column(JSON)  # list of {cause, confidence}
    evidence = Column(JSON)  # extracted patterns from logs
    classifier_version = Column(String(50), default="rule_based_v1")
    model_scores = Column(JSON)  # raw model outputs
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    flaky_test = relationship("FlakyTest", back_populates="analyses")


class FixProposal(Base):
    __tablename__ = "fix_proposals"

    id = Column(Integer, primary_key=True, index=True)
    flaky_test_id = Column(Integer, ForeignKey("flaky_tests.id"), nullable=False)
    status = Column(SAEnum(FixStatus), default=FixStatus.pending)
    root_cause = Column(SAEnum(FlakinessCause))
    patch_diff = Column(Text)
    explanation = Column(Text)
    affected_files = Column(JSON)
    confidence = Column(Float)
    pr_url = Column(String(500))
    pr_number = Column(Integer)
    feedback_accepted = Column(Boolean)
    feedback_note = Column(Text)
    llm_model = Column(String(100))
    context_used = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    flaky_test = relationship("FlakyTest", back_populates="fixes")