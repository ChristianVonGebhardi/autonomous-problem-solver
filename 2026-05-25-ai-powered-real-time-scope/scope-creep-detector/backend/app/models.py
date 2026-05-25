import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Text, Float, DateTime, Boolean, 
    ForeignKey, Integer, JSON, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base
import enum


class SeverityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationStatus(str, enum.Enum):
    PENDING = "pending"
    CHANGE_ORDER_CREATED = "change_order_created"
    DISMISSED = "dismissed"


class ChangeOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    hourly_rate = Column(Float, default=150.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    contracts = relationship("Contract", back_populates="owner")
    messages = relationship("Message", back_populates="owner")


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    client_name = Column(String(255), nullable=False)
    file_path = Column(String(1000), nullable=True)
    file_name = Column(String(500), nullable=True)
    raw_text = Column(Text, nullable=True)
    status = Column(String(50), default="processing")  # processing, active, archived
    project_value = Column(Float, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="contracts")
    clauses = relationship("ContractClause", back_populates="contract", cascade="all, delete-orphan")
    violations = relationship("Violation", back_populates="contract")
    messages = relationship("Message", back_populates="contract")


class ContractClause(Base):
    __tablename__ = "contract_clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)  # text-embedding-3-large dim
    clause_type = Column(String(100), nullable=True)  # scope, payment, timeline, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    contract = relationship("Contract", back_populates="clauses")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)
    source = Column(String(50), default="manual")  # manual, gmail, slack, linear
    sender_name = Column(String(255), nullable=True)
    sender_email = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    analyzed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="messages")
    contract = relationship("Contract", back_populates="messages")
    violations = relationship("Violation", back_populates="message")


class Violation(Base):
    __tablename__ = "violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    violation_score = Column(Float, nullable=False)  # 0.0 - 1.0
    severity = Column(SAEnum(SeverityLevel), nullable=False)
    summary = Column(Text, nullable=False)
    out_of_scope_work = Column(Text, nullable=False)
    cited_clauses = Column(JSON, nullable=True)  # list of clause excerpts
    estimated_hours = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    status = Column(SAEnum(ViolationStatus), default=ViolationStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)

    contract = relationship("Contract", back_populates="violations")
    message = relationship("Message", back_populates="violations")
    change_orders = relationship("ChangeOrder", back_populates="violation")


class ChangeOrder(Base):
    __tablename__ = "change_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    violation_id = Column(UUID(as_uuid=True), ForeignKey("violations.id"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    scope_addition = Column(Text, nullable=False)
    estimated_hours = Column(Float, nullable=False)
    hourly_rate = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    terms = Column(Text, nullable=True)
    pdf_path = Column(String(1000), nullable=True)
    status = Column(SAEnum(ChangeOrderStatus), default=ChangeOrderStatus.DRAFT)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    violation = relationship("Violation", back_populates="change_orders")