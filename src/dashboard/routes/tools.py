"""Tools dashboard route — /tools endpoints.

Shows available tools and usage statistics.
"""

from collections import namedtuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from timmy.tools import get_all_available_tools
from dashboard.templating import templates

router = APIRouter(tags=["tools"])

_AgentView = namedtuple("AgentView", ["name", "status", "tools", "stats"])
_ToolView = namedtuple("ToolView", ["name", "description"])
_Stats = namedtuple("Stats", ["total_calls"])


def _build_agent_tools():
    """Build agent capability list from the available tools registry."""
    available = get_all_available_tools()
    if not available:
        return []

    tool_views = [
        _ToolView(name=name, description=getattr(fn, "__doc__", "") or name)
        for name, fn in available.items()
    ]

    return [
        _AgentView(name="Timmy", status="idle", tools=tool_views, stats=_Stats(total_calls=0))
    ]


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    """Render the tools dashboard page."""
    available_tools = get_all_available_tools()
    agent_tools = _build_agent_tools()
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
