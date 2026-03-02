"""Tools dashboard route — /tools endpoints.

Shows available tools and usage statistics.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from brain.client import BrainClient
from timmy.tools import get_all_available_tools

router = APIRouter(tags=["tools"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    """Render the tools dashboard page."""
    available_tools = get_all_available_tools()
    brain = BrainClient()
    
    # Get recent tool usage from brain memory
    recent_memories = await brain.get_recent(hours=24, limit=50, sources=["timmy"])
    
    # Simple tool list - no persona filtering
    tool_list = []
    for tool_id, tool_info in available_tools.items():
        tool_list.append({
            "id": tool_id,
            "name": tool_info.get("name", tool_id),
            "description": tool_info.get("description", ""),
            "available": True,
        })
    
    return templates.TemplateResponse(
        "tools.html",
        {
            "request": request,
            "tools": tool_list,
            "recent_activity": len(recent_memories),
        }
    )
