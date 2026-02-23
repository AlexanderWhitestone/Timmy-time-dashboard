"""Tools dashboard route — /tools endpoints.

Provides a dashboard page showing available tools, which agents have access
to which tools, and usage statistics.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swarm import registry as swarm_registry
from swarm.personas import PERSONAS
from timmy.tools import get_all_available_tools, get_tool_stats

router = APIRouter(tags=["tools"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    """Render the tools dashboard page."""
    # Get all available tools
    available_tools = get_all_available_tools()
    
    # Get registered agents and their personas
    agents = swarm_registry.list_agents()
    agent_tools = []
    
    for agent in agents:
        # Determine which tools this agent has based on its capabilities/persona
        tools_for_agent = []
        
        # Check if it's a persona by name
        persona_id = None
        for pid, pdata in PERSONAS.items():
            if pdata["name"].lower() == agent.name.lower():
                persona_id = pid
                break
        
        if persona_id:
            # Get tools for this persona
            for tool_id, tool_info in available_tools.items():
                if persona_id in tool_info["available_in"]:
                    tools_for_agent.append({
                        "id": tool_id,
                        "name": tool_info["name"],
                        "description": tool_info["description"],
                    })
        elif agent.name.lower() == "timmy":
            # Timmy has all tools
            for tool_id, tool_info in available_tools.items():
                tools_for_agent.append({
                    "id": tool_id,
                    "name": tool_info["name"],
                    "description": tool_info["description"],
                })
        
        # Get tool stats for this agent
        stats = get_tool_stats(agent.id)
        
        agent_tools.append({
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "tools": tools_for_agent,
            "stats": stats,
        })
    
    # Calculate overall stats
    total_calls = sum(a["stats"]["total_calls"] for a in agent_tools if a["stats"])
    
    return templates.TemplateResponse(
        request,
        "tools.html",
        {
            "page_title": "Tools & Capabilities",
            "available_tools": available_tools,
            "agent_tools": agent_tools,
            "total_calls": total_calls,
        },
    )


@router.get("/tools/api/stats")
async def tools_api_stats():
    """Return tool usage statistics as JSON."""
    return {
        "all_stats": get_tool_stats(),
        "available_tools": list(get_all_available_tools().keys()),
    }
