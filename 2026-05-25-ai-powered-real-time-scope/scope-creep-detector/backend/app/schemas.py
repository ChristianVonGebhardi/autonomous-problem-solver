from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from app.models import SeverityLevel, ViolationStatus, ChangeOrderStatus


# ---- Auth ----

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    company_name: Optional[str] = None
    hourly_rate: float = 150.0


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    company_name: Optional[str]
    hourly_rate: float
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Contracts ----

class ContractOut(BaseModel):
    id: UUID
    title: str
    client_name: str
    file_name: Optional[str]
    status: str
    project_value: Optional[float]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime
    clause_count: int = 0

    model_config = {"from_attributes": True}


class ContractDetail(ContractOut):
    raw_text: Optional[str]


# ---- Messages ----

class MessageCreate(BaseModel):
    contract_id: UUID
    content: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    source: str = "manual"


class MessageOut(BaseModel):
    id: UUID
    contract_id: UUID
    source: str
    sender_name: Optional[str]
    sender_email: Optional[str]
    subject: Optional[str]
    content: str
    analyzed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Violations ----

class CitedClause(BaseModel):
    text: str
    relevance: str


class ViolationOut(BaseModel):
    id: UUID
    contract_id: UUID
    message_id: UUID
    violation_score: float
    severity: SeverityLevel
    summary: str
    out_of_scope_work: str
    cited_clauses: Optional[List[Any]]
    estimated_hours: Optional[float]
    estimated_cost: Optional[float]
    status: ViolationStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Change Orders ----

class ChangeOrderOut(BaseModel):
    id: UUID
    violation_id: UUID
    title: str
    description: str
    scope_addition: str
    estimated_hours: float
    hourly_rate: float
    total_cost: float
    terms: Optional[str]
    pdf_path: Optional[str]
    status: ChangeOrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangeOrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scope_addition: Optional[str] = None
    estimated_hours: Optional[float] = None
    hourly_rate: Optional[float] = None
    terms: Optional[str] = None


# ---- Dashboard ----

class DashboardStats(BaseModel):
    total_contracts: int
    active_contracts: int
    total_violations: int
    pending_violations: int
    total_change_orders: int
    approved_change_orders: int
    recovered_revenue: float
    potential_revenue: float
    monthly_recovered: float


# ---- WebSocket ----

class WSMessage(BaseModel):
    type: str  # violation_detected, change_order_created, etc.
    data: Any