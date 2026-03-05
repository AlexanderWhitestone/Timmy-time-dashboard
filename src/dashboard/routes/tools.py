"""Tools dashboard route — /tools endpoints.

Shows available tools and usage statistics.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from timmy.tools import get_all_available_tools
from dashboard.templating import templates

router = APIRouter(tags=["tools"])


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    """Render the tools dashboard page."""
    available_tools = get_all_available_tools()

    # Build agent tools list from the available tools
    agent_tools = []

    # Calculate total calls (placeholder — would come from brain memory)
    total_calls = 0

    return templates.TemplateResponse(
        "tools.html",
        {
            "request": request,
            "available_tools": available_tools,
            "agent_tools": agent_tools,
            "total_calls": total_calls,
        },
    )


@router.get("/tools/api/stats", response_class=JSONResponse)
async def tools_api_stats():
    """Return tool statistics as JSON."""
    available_tools = get_all_available_tools()

    return {
        "all_stats": {},
        "available_tools": list(available_tools.keys()),
    }
