"""
Iris Web Dashboard

Simple HTML dashboard for monitoring the network.
Includes public chat interface with rate limiting.
"""

from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .database import db
from .node_registry import node_registry
from .account_service import account_service
from shared.models import TaskMode

# Router for dashboard routes
router = APIRouter(tags=["dashboard"])

# Templates directory
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


# =============================================================================
# Rate Limiting for Public Chat
# =============================================================================

# In-memory rate limiting (reset on server restart)
# In production, use Redis or database for persistence
rate_limit_store: dict[str, dict] = defaultdict(lambda: {
    "messages_sent": 0,
    "first_message_at": None,
    "account_verified": False
})

# Constants
ANONYMOUS_LIMIT = 1
VERIFIED_LIMIT = 3
RATE_LIMIT_WINDOW_HOURS = 24


class ChatRequest(BaseModel):
    """Request model for chat messages."""
    prompt: str
    account_key: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat messages."""
    response: str
    messages_remaining: int


def get_client_id(request: Request) -> str:
    """Get a unique identifier for the client (IP-based)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(client_id: str, account_key: Optional[str] = None) -> tuple[bool, int]:
    """
    Check if the client can send a message.

    Returns:
        Tuple of (can_send, messages_remaining)
    """
    client_data = rate_limit_store[client_id]

    # Reset if window has passed
    if client_data["first_message_at"]:
        window_start = datetime.fromisoformat(client_data["first_message_at"])
        if datetime.utcnow() - window_start > timedelta(hours=RATE_LIMIT_WINDOW_HOURS):
            client_data["messages_sent"] = 0
            client_data["first_message_at"] = None
            client_data["account_verified"] = False

    # Determine limit based on account verification
    limit = VERIFIED_LIMIT if client_data["account_verified"] else ANONYMOUS_LIMIT

    messages_sent = client_data["messages_sent"]
    remaining = max(0, limit - messages_sent)

    return messages_sent < limit, remaining


def record_message(client_id: str):
    """Record that a message was sent."""
    client_data = rate_limit_store[client_id]

    if not client_data["first_message_at"]:
        client_data["first_message_at"] = datetime.utcnow().isoformat()

    client_data["messages_sent"] += 1


async def verify_and_upgrade_limit(client_id: str, account_key: str) -> bool:
    """Verify account key and upgrade rate limit if valid."""
    account_info = await account_service.get_account_by_key(account_key)
    if account_info:
        rate_limit_store[client_id]["account_verified"] = True
        return True
    return False


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard page."""
    # Get stats
    stats = await db.get_stats()
    stats["nodes_online"] = node_registry.connected_count

    # Get connected nodes
    connected_nodes = []
    for node in node_registry.get_all_nodes():
        db_node = await db.get_node_by_id(node.node_id)
        connected_nodes.append({
            "id": node.node_id,
            "model_name": node.model_name,
            "reputation": db_node.get("reputation", 100) if db_node else 100,
            "current_load": node.current_load,
            "vram_gb": node.vram_gb,
            "connected_at": node.connected_at.strftime("%Y-%m-%d %H:%M"),
            "is_online": True,
            # New fields for intelligent task assignment
            "gpu_name": node.gpu_name,
            "model_params": node.model_params,
            "model_quantization": node.model_quantization,
            "tokens_per_second": node.tokens_per_second,
            "node_tier": node.node_tier.value if hasattr(node.node_tier, 'value') else node.node_tier
        })

    # Get all nodes for leaderboard
    all_nodes = await db.get_all_nodes()
    leaderboard = [
        {
            "rank": i + 1,
            "id": n["id"],
            "model_name": n.get("model_name", "unknown"),
            "reputation": n.get("reputation", 100),
            "tasks_completed": n.get("total_tasks_completed", 0),
            "is_online": node_registry.is_online(n["id"])
        }
        for i, n in enumerate(all_nodes[:10])
    ]

    # Get recent tasks
    recent_tasks = await db.get_recent_tasks(limit=10)
    tasks = [
        {
            "id": t["id"],
            "status": t.get("status", "unknown"),
            "mode": t.get("mode", "unknown"),
            "difficulty": t.get("difficulty", "simple"),
            "created_at": t.get("created_at", "")[:19] if t.get("created_at") else "",
            "prompt_preview": (t.get("original_prompt", "")[:50] + "...") if t.get("original_prompt") else ""
        }
        for t in recent_tasks
    ]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "nodes": connected_nodes,
            "leaderboard": leaderboard,
            "tasks": tasks
        }
    )


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Render the public chat page."""
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "nodes_online": node_registry.connected_count
        }
    )


@router.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: Request, chat_request: ChatRequest):
    """
    Public chat endpoint with rate limiting.

    - Without account key: 1 message per 24h
    - With valid account key: 3 messages per 24h
    """
    client_id = get_client_id(request)

    # If account key provided, try to verify and upgrade limit
    if chat_request.account_key:
        await verify_and_upgrade_limit(client_id, chat_request.account_key)

    # Check rate limit
    can_send, remaining = check_rate_limit(client_id)

    if not can_send:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Message limit reached. Please try again later or use an Account Key."
        )

    # Check if any nodes are available
    if node_registry.connected_count == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No inference nodes currently available. Please try again later."
        )

    # Process the inference request
    from .task_orchestrator import task_orchestrator

    try:
        # Create task (using a system user for public chat)
        task = await task_orchestrator.create_task(
            user_id="public_chat",
            prompt=chat_request.prompt,
            mode=TaskMode.SUBTASKS
        )

        # Wait for task completion (with timeout)
        import asyncio
        max_wait = 60  # 60 seconds timeout
        poll_interval = 0.5

        for _ in range(int(max_wait / poll_interval)):
            task_data = await db.get_task_by_id(task["id"])
            if task_data and task_data.get("status") == "completed":
                record_message(client_id)
                _, new_remaining = check_rate_limit(client_id)
                return ChatResponse(
                    response=task_data.get("final_response", "Task completed but no response available."),
                    messages_remaining=new_remaining
                )
            elif task_data and task_data.get("status") == "failed":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Task processing failed. Please try again."
                )
            await asyncio.sleep(poll_interval)

        # Timeout reached
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The network may be busy."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}"
        )


def setup_dashboard(app):
    """
    Set up dashboard routes on the FastAPI app.

    Call this from main.py to enable the dashboard.
    """
    app.include_router(router)
