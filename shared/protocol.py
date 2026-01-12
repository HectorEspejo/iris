"""
Iris WebSocket Protocol

Message definitions for coordinator <-> node communication.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import json


class MessageType(str, Enum):
    """Types of messages in the WebSocket protocol."""
    # Node -> Coordinator
    NODE_REGISTER = "node_register"
    NODE_HEARTBEAT = "node_heartbeat"
    NODE_DISCONNECT = "node_disconnect"
    TASK_RESULT = "task_result"
    TASK_ERROR = "task_error"
    TASK_STREAM = "task_stream"  # Streaming chunks during inference
    CLASSIFY_RESULT = "classify_result"
    CLASSIFY_ERROR = "classify_error"

    # Coordinator -> Node
    REGISTER_ACK = "register_ack"
    HEARTBEAT_ACK = "heartbeat_ack"
    TASK_ASSIGN = "task_assign"
    CLASSIFY_ASSIGN = "classify_assign"

    # Bidirectional
    ERROR = "error"


# =============================================================================
# Payload Models
# =============================================================================

class NodeRegisterPayload(BaseModel):
    """Payload for NODE_REGISTER message."""
    node_id: str
    public_key: str
    # Account key (Mullvad-style) - required for registration
    account_key: Optional[str] = None
    # Legacy enrollment token (deprecated, use account_key instead)
    enrollment_token: Optional[str] = None
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


class RegisterAckPayload(BaseModel):
    """Payload for REGISTER_ACK message."""
    success: bool
    coordinator_public_key: str
    message: Optional[str] = None


class NodeHeartbeatPayload(BaseModel):
    """Payload for NODE_HEARTBEAT message."""
    node_id: str
    current_load: int = 0  # Number of tasks currently processing
    uptime_seconds: int = 0
    # Timestamp for RTT/latency measurement
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    # Extended stats for real-time updates
    gpu_vram_free: Optional[float] = None  # Current free VRAM
    tokens_per_second: Optional[float] = None  # Recent performance
    latency_avg_ms: Optional[float] = None  # Recent latency


class HeartbeatAckPayload(BaseModel):
    """Payload for HEARTBEAT_ACK message."""
    success: bool
    server_time: datetime = Field(default_factory=datetime.utcnow)


class TaskAssignPayload(BaseModel):
    """Payload for TASK_ASSIGN message."""
    subtask_id: str
    task_id: str
    encrypted_prompt: str  # Encrypted with node's public key
    timeout_seconds: int = 60
    enable_streaming: bool = False  # If True, node sends TASK_STREAM chunks


class TaskResultPayload(BaseModel):
    """Payload for TASK_RESULT message."""
    subtask_id: str
    task_id: str
    encrypted_response: str  # Encrypted with coordinator's public key
    execution_time_ms: int


class TaskErrorPayload(BaseModel):
    """Payload for TASK_ERROR message."""
    subtask_id: str
    task_id: str
    error_code: str
    error_message: str


class TaskStreamPayload(BaseModel):
    """Payload for TASK_STREAM message (streaming chunks during inference)."""
    subtask_id: str
    task_id: str
    encrypted_chunk: str  # Encrypted chunk of generated text
    chunk_index: int = 0  # Sequential index of this chunk


class ClassifyAssignPayload(BaseModel):
    """Payload for CLASSIFY_ASSIGN message (Coordinator -> Node)."""
    classify_id: str
    encrypted_prompt: str  # Encrypted classification prompt
    timeout_seconds: int = 15


class ClassifyResultPayload(BaseModel):
    """Payload for CLASSIFY_RESULT message (Node -> Coordinator)."""
    classify_id: str
    encrypted_response: str  # Encrypted classification result
    execution_time_ms: int


class ClassifyErrorPayload(BaseModel):
    """Payload for CLASSIFY_ERROR message (Node -> Coordinator)."""
    classify_id: str
    error_code: str
    error_message: str


class ErrorPayload(BaseModel):
    """Payload for generic ERROR message."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


# =============================================================================
# Protocol Message
# =============================================================================

class ProtocolMessage(BaseModel):
    """
    Base message format for all WebSocket communication.

    Example:
        {
            "type": "node_register",
            "payload": {...},
            "timestamp": "2025-01-09T12:00:00Z",
            "signature": "base64..."
        }
    """
    type: MessageType
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    signature: Optional[str] = None  # Optional signature for verification

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str) -> "ProtocolMessage":
        """Deserialize message from JSON string."""
        return cls.model_validate_json(data)

    @classmethod
    def create(
        cls,
        msg_type: MessageType,
        payload: BaseModel,
        signature: Optional[str] = None
    ) -> "ProtocolMessage":
        """Create a protocol message with a typed payload."""
        return cls(
            type=msg_type,
            payload=payload.model_dump(),
            signature=signature
        )


# =============================================================================
# Helper Functions
# =============================================================================

def parse_payload(msg: ProtocolMessage, payload_class: type[BaseModel]) -> BaseModel:
    """
    Parse a message payload into the expected type.

    Args:
        msg: The protocol message
        payload_class: The Pydantic model class for the payload

    Returns:
        Parsed payload instance

    Raises:
        ValueError: If payload doesn't match expected schema
    """
    return payload_class.model_validate(msg.payload)


def create_error_message(code: str, message: str, details: Optional[dict] = None) -> ProtocolMessage:
    """Create an error message."""
    return ProtocolMessage.create(
        MessageType.ERROR,
        ErrorPayload(code=code, message=message, details=details)
    )
