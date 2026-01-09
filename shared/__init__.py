"""
ClubAI Shared Module

Common models, protocols, and utilities shared between coordinator, node agents, and clients.
"""

from .models import (
    User,
    UserCreate,
    UserLogin,
    Node,
    NodeCapabilities,
    Task,
    TaskCreate,
    TaskStatus,
    Subtask,
    SubtaskStatus,
    InferenceRequest,
    InferenceResponse,
    ReputationChange,
    EarningRecord,
)
from .protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    NodeHeartbeatPayload,
    TaskAssignPayload,
    TaskResultPayload,
    TaskErrorPayload,
)
from .crypto_utils import (
    KeyPair,
    generate_keypair,
    encrypt_for_recipient,
    decrypt_from_sender,
)

__all__ = [
    # Models
    "User",
    "UserCreate",
    "UserLogin",
    "Node",
    "NodeCapabilities",
    "Task",
    "TaskCreate",
    "TaskStatus",
    "Subtask",
    "SubtaskStatus",
    "InferenceRequest",
    "InferenceResponse",
    "ReputationChange",
    "EarningRecord",
    # Protocol
    "MessageType",
    "ProtocolMessage",
    "NodeRegisterPayload",
    "NodeHeartbeatPayload",
    "TaskAssignPayload",
    "TaskResultPayload",
    "TaskErrorPayload",
    # Crypto
    "KeyPair",
    "generate_keypair",
    "encrypt_for_recipient",
    "decrypt_from_sender",
]
