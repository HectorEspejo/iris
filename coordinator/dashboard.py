"""
ClubAI Web Dashboard

Simple HTML dashboard for monitoring the network.
"""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .database import db
from .node_registry import node_registry

# Router for dashboard routes
router = APIRouter(tags=["dashboard"])

# Templates directory
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


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


def setup_dashboard(app):
    """
    Set up dashboard routes on the FastAPI app.

    Call this from main.py to enable the dashboard.
    """
    app.include_router(router)
