"""
Iris Pydantic Models

Shared data models for users, nodes, tasks, and economic tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


# =============================================================================
# User Models
# =============================================================================

class MembershipStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserLogin(UserBase):
    password: str


class User(UserBase):
    id: str = Field(default_factory=generate_id)
    public_key: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    membership_status: MembershipStatus = MembershipStatus.ACTIVE
    monthly_quota: int = 1000

    class Config:
        from_attributes = True


class UserInDB(User):
    password_hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# =============================================================================
# Account Models (Mullvad-style)
# =============================================================================

class AccountStatus(str, Enum):
    """Account status states."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Account(BaseModel):
    """Account for node operators (Mullvad-style)."""
    id: str = Field(default_factory=generate_id)
    account_key_prefix: str  # First 4 digits for partial identification
    status: AccountStatus = AccountStatus.ACTIVE
    total_earnings: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AccountCreateResponse(BaseModel):
    """
    Response when creating a new account.

    IMPORTANT: The account_key is only shown ONCE at creation time.
    """
    account_key: str  # Full key, only shown once!
    account: Account


class AccountInfo(BaseModel):
    """Account information with node count."""
    id: str
    account_key_prefix: str
    status: AccountStatus
    total_earnings: float
    node_count: int
    created_at: datetime
    last_activity_at: Optional[datetime] = None


class AccountWithNodes(BaseModel):
    """Account with all its linked nodes."""
    account: Account
    nodes: list["Node"] = []
    total_reputation: float = 0.0


# =============================================================================
# Node Models
# =============================================================================

class NodeCapabilities(BaseModel):
    """Capabilities reported by a node during registration."""
    lmstudio_port: int = 1234
    model_name: str
    max_context: int = 8192
    vram_gb: float
    available_hours: list[int] = Field(default_factory=lambda: list(range(24)))
    # Extended capabilities for intelligent task assignment
    gpu_name: str = "Unknown"
    gpu_vram_free: float = 0.0
    model_params: float = 7.0  # Billions of parameters
    model_quantization: str = "Q4"
    tokens_per_second: float = 0.0
    latency_avg_ms: float = 0.0


class NodeBase(BaseModel):
    public_key: str
    capabilities: NodeCapabilities


class NodeCreate(NodeBase):
    owner_id: str


class Node(NodeBase):
    id: str = Field(default_factory=generate_id)
    owner_id: Optional[str] = None  # Legacy user reference (admin only)
    account_id: Optional[str] = None  # Mullvad-style account reference
    reputation: float = 100.0
    total_tasks_completed: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Update forward reference for AccountWithNodes
AccountWithNodes.model_rebuild()


class NodeStatus(BaseModel):
    """Runtime status of a connected node."""
    node_id: str
    is_online: bool
    current_load: int = 0  # Number of active tasks
    latency_ms: Optional[float] = None


# =============================================================================
# Task Models
# =============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some subtasks failed


class TaskDifficulty(str, Enum):
    """Difficulty level for task classification."""
    SIMPLE = "simple"       # Short questions, simple translations
    COMPLEX = "complex"     # Analysis, summaries, simple code
    ADVANCED = "advanced"   # Complex reasoning, advanced code, math


class NodeTier(str, Enum):
    """Node capability tier for task matching."""
    BASIC = "basic"         # Small GPUs, models <7B
    STANDARD = "standard"   # Medium GPUs, models 7B-13B
    PREMIUM = "premium"     # Powerful GPUs, models 30B+


class TaskMode(str, Enum):
    CONSENSUS = "consensus"  # Same task to multiple nodes
    SUBTASKS = "subtasks"    # Divide into subtasks
    CONTEXT = "context"      # Divide long context


class TaskCreate(BaseModel):
    prompt: str
    mode: TaskMode = TaskMode.SUBTASKS


class Task(BaseModel):
    id: str = Field(default_factory=generate_id)
    user_id: str
    mode: TaskMode
    difficulty: TaskDifficulty = TaskDifficulty.SIMPLE
    original_prompt: str
    encrypted_prompt: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    final_response: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Subtask(BaseModel):
    id: str = Field(default_factory=generate_id)
    task_id: str
    node_id: Optional[str] = None
    prompt: str
    encrypted_prompt: Optional[str] = None
    response: Optional[str] = None
    encrypted_response: Optional[str] = None
    status: SubtaskStatus = SubtaskStatus.PENDING
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None

    class Config:
        from_attributes = True


# =============================================================================
# Inference Request/Response
# =============================================================================

class InferenceRequest(BaseModel):
    """Request sent from client to coordinator."""
    prompt: str
    mode: TaskMode = TaskMode.SUBTASKS
    encrypted: bool = False  # If true, prompt is already encrypted


class InferenceResponse(BaseModel):
    """Response from coordinator to client."""
    task_id: str
    status: TaskStatus
    response: Optional[str] = None
    subtasks_completed: int = 0
    subtasks_total: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None


# =============================================================================
# Reputation Models
# =============================================================================

class ReputationChangeReason(str, Enum):
    TASK_COMPLETED = "task_completed"
    TASK_FAST = "task_fast"
    TASK_TIMEOUT = "task_timeout"
    TASK_INVALID = "task_invalid"
    UPTIME_HOUR = "uptime_hour"
    UPTIME_BROKEN = "uptime_broken"
    WEEKLY_DECAY = "weekly_decay"


class ReputationChange(BaseModel):
    id: Optional[int] = None
    node_id: str
    change: float
    reason: ReputationChangeReason
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


# =============================================================================
# Economic Models
# =============================================================================

class EconomicPeriod(BaseModel):
    id: str = Field(default_factory=generate_id)
    month: str  # Format: "2025-01"
    total_pool: float
    distributed: bool = False
    distributed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EarningRecord(BaseModel):
    period_id: str
    node_id: str
    reputation_snapshot: float
    share_percentage: float
    amount: float

    class Config:
        from_attributes = True
