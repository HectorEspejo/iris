"""
Iris Coordinator - Main Application

FastAPI server that orchestrates the distributed inference network.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from pydantic import BaseModel as PydanticBaseModel
from fastapi.middleware.cors import CORSMiddleware
import structlog

from shared.models import (
    User,
    UserCreate,
    UserLogin,
    TokenResponse,
    InferenceRequest,
    InferenceResponse,
    TaskStatus,
)
from shared.protocol import MessageType, ProtocolMessage

from .database import db
from .auth import register_user, login_user, get_current_user, get_user_info
from .crypto import coordinator_crypto
from .node_registry import node_registry
from .node_tokens import NodeTokenManager, TokenValidationResult

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global token manager - initialized on startup
token_manager: NodeTokenManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global token_manager

    # Startup
    logger.info("coordinator_starting")
    await db.connect()
    coordinator_crypto.initialize()
    token_manager = NodeTokenManager(db)
    # Connect token manager to node registry for enrollment validation
    node_registry.set_token_manager(token_manager)
    logger.info(
        "coordinator_started",
        public_key=coordinator_crypto.public_key[:16] + "..."
    )

    yield

    # Shutdown
    logger.info("coordinator_shutting_down")
    await db.disconnect()
    logger.info("coordinator_stopped")


# Create FastAPI app
app = FastAPI(
    title="Iris Coordinator",
    description="Central coordinator for the Iris distributed inference network",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include dashboard routes
from .dashboard import setup_dashboard
setup_dashboard(app)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "nodes_connected": node_registry.connected_count
    }


# =============================================================================
# Authentication Endpoints
# =============================================================================

@app.post("/auth/register", response_model=User)
async def api_register(user_data: UserCreate):
    """Register a new user."""
    return await register_user(user_data)


@app.post("/auth/login", response_model=TokenResponse)
async def api_login(credentials: UserLogin):
    """Login and receive access token."""
    return await login_user(credentials)


@app.get("/auth/me")
async def api_me(user: User = Depends(get_current_user)):
    """Get current user information."""
    return await get_user_info(user)


# =============================================================================
# Inference Endpoints
# =============================================================================

@app.post("/inference", response_model=InferenceResponse)
async def api_inference(
    request: InferenceRequest,
    user: User = Depends(get_current_user)
):
    """
    Submit an inference request.

    The request will be divided into subtasks and distributed to available nodes.
    """
    # Import here to avoid circular imports
    from .task_orchestrator import task_orchestrator

    try:
        task = await task_orchestrator.create_task(
            user_id=user.id,
            prompt=request.prompt,
            mode=request.mode
        )

        return InferenceResponse(
            task_id=task["id"],
            status=TaskStatus(task["status"]),
            subtasks_completed=0,
            subtasks_total=len(await db.get_subtasks_by_task(task["id"])),
            created_at=task["created_at"]
        )

    except Exception as e:
        logger.error("inference_request_failed", error=str(e), user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create inference task: {str(e)}"
        )


@app.get("/inference/{task_id}", response_model=InferenceResponse)
async def api_get_task(
    task_id: str,
    user: User = Depends(get_current_user)
):
    """Get the status of an inference task."""
    task = await db.get_task_by_id(task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task["user_id"] != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this task"
        )

    subtasks = await db.get_subtasks_by_task(task_id)
    completed = sum(1 for s in subtasks if s["status"] == "completed")

    return InferenceResponse(
        task_id=task["id"],
        status=TaskStatus(task["status"]),
        response=task.get("final_response"),
        subtasks_completed=completed,
        subtasks_total=len(subtasks),
        created_at=task["created_at"],
        completed_at=task.get("completed_at")
    )


# =============================================================================
# Statistics Endpoints
# =============================================================================

@app.get("/stats")
async def api_stats():
    """Get network statistics."""
    stats = await db.get_stats()
    stats["nodes_online"] = node_registry.connected_count
    return stats


@app.get("/reputation")
async def api_reputation():
    """Get node reputation leaderboard."""
    nodes = await db.get_all_nodes()
    return [
        {
            "node_id": n["id"],
            "model_name": n["model_name"],
            "reputation": n["reputation"],
            "tasks_completed": n["total_tasks_completed"],
            "is_online": node_registry.is_online(n["id"])
        }
        for n in nodes[:20]  # Top 20
    ]


@app.get("/nodes")
async def api_nodes(user: User = Depends(get_current_user)):
    """Get list of active nodes."""
    connected = node_registry.get_all_nodes()
    return [
        {
            "node_id": n.node_id,
            "model_name": n.model_name,
            "max_context": n.max_context,
            "vram_gb": n.vram_gb,
            "current_load": n.current_load,
            "connected_at": n.connected_at
        }
        for n in connected
    ]


@app.get("/history")
async def api_history(
    user: User = Depends(get_current_user),
    limit: int = 50
):
    """Get user's task history."""
    tasks = await db.get_tasks_by_user(user.id, limit=limit)
    return tasks


# =============================================================================
# Node Enrollment Token Endpoints
# =============================================================================


class ValidateTokenRequest(PydanticBaseModel):
    """Request to validate an enrollment token."""
    token: str


class GenerateTokenRequest(PydanticBaseModel):
    """Request to generate a new enrollment token."""
    label: Optional[str] = None
    expires_in_days: Optional[int] = None


class GenerateTokenResponse(PydanticBaseModel):
    """Response after generating an enrollment token."""
    token: str
    id: str
    expires_at: Optional[str] = None


@app.post("/nodes/validate-token", response_model=TokenValidationResult)
async def api_validate_token(request: ValidateTokenRequest):
    """
    Validate an enrollment token.

    This endpoint is public and used by the installer script to verify
    that a token is valid before proceeding with installation.
    """
    return await token_manager.validate(request.token)


@app.post("/admin/tokens/generate", response_model=GenerateTokenResponse)
async def api_generate_token(
    request: GenerateTokenRequest,
    user: User = Depends(get_current_user)
):
    """
    Generate a new enrollment token.

    Requires authentication. In production, should require admin role.
    """
    token, token_id = await token_manager.generate(
        label=request.label,
        expires_in_days=request.expires_in_days
    )

    # Calculate expiration date if provided
    expires_at = None
    if request.expires_in_days:
        from datetime import datetime, timedelta
        expires_at = (datetime.utcnow() + timedelta(days=request.expires_in_days)).isoformat()

    return GenerateTokenResponse(
        token=token,
        id=token_id,
        expires_at=expires_at
    )


@app.get("/admin/tokens")
async def api_list_tokens(
    user: User = Depends(get_current_user),
    include_used: bool = True,
    include_revoked: bool = False
):
    """
    List all enrollment tokens.

    Requires authentication. In production, should require admin role.
    """
    tokens = await token_manager.list_tokens(
        include_used=include_used,
        include_revoked=include_revoked
    )
    return [t.model_dump() for t in tokens]


@app.get("/admin/tokens/{token_id}")
async def api_get_token(
    token_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get information about a specific token.

    Requires authentication. In production, should require admin role.
    """
    token_info = await token_manager.get_token_info(token_id)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    return token_info.model_dump()


@app.delete("/admin/tokens/{token_id}")
async def api_revoke_token(
    token_id: str,
    user: User = Depends(get_current_user)
):
    """
    Revoke an enrollment token.

    Requires authentication. In production, should require admin role.
    """
    success = await token_manager.revoke(token_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    return {"success": True, "message": f"Token {token_id} revoked"}


# =============================================================================
# WebSocket Endpoint for Nodes
# =============================================================================

@app.websocket("/nodes/connect")
async def websocket_node(websocket: WebSocket):
    """
    WebSocket endpoint for node connections.

    Protocol:
    1. Node sends NODE_REGISTER with capabilities
    2. Coordinator responds with REGISTER_ACK
    3. Node sends periodic NODE_HEARTBEAT
    4. Coordinator sends TASK_ASSIGN when work is available
    5. Node responds with TASK_RESULT or TASK_ERROR
    """
    await websocket.accept()
    node_id: str | None = None

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message = ProtocolMessage.from_json(data)

            # Handle by message type
            if message.type == MessageType.NODE_REGISTER:
                node_id = await node_registry.handle_register(websocket, message)
                if not node_id:
                    await websocket.close(code=4001, reason="Registration failed")
                    return

            elif message.type == MessageType.NODE_HEARTBEAT:
                if node_id:
                    await node_registry.handle_heartbeat(node_id, message)

            elif message.type == MessageType.TASK_RESULT:
                if node_id:
                    # Import here to avoid circular imports
                    from .task_orchestrator import task_orchestrator
                    await task_orchestrator.handle_task_result(node_id, message)

            elif message.type == MessageType.TASK_ERROR:
                if node_id:
                    from .task_orchestrator import task_orchestrator
                    await task_orchestrator.handle_task_error(node_id, message)

            elif message.type == MessageType.NODE_DISCONNECT:
                break

            else:
                logger.warning(
                    "unknown_message_type",
                    type=message.type,
                    node_id=node_id
                )

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", node_id=node_id)
    except Exception as e:
        logger.error("websocket_error", error=str(e), node_id=node_id)
    finally:
        if node_id:
            await node_registry.handle_disconnect(node_id)


# =============================================================================
# Run Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "coordinator.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
