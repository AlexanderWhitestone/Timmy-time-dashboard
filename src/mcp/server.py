"""MCP (Model Context Protocol) Server.

Implements the MCP protocol for tool discovery and execution.
Agents communicate with this server to discover and invoke tools.

The server can run:
1. In-process (direct method calls) — fastest, for local agents
2. HTTP API — for external clients
3. Stdio — for subprocess-based agents
"""

import asyncio
import json
import logging
from typing import Any, Optional

from mcp.registry import tool_registry

logger = logging.getLogger(__name__)


class MCPServer:
    """Model Context Protocol server for tool management.
    
    Provides standard MCP endpoints:
    - list_tools: Discover available tools
    - call_tool: Execute a tool
    - get_schema: Get tool input/output schemas
    """
    
    def __init__(self) -> None:
        self.registry = tool_registry
        logger.info("MCP Server initialized")
    
    def list_tools(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
    ) -> list[dict]:
        """List available tools.
        
        MCP Protocol: tools/list
        """
        tools = self.registry.discover(
            query=query,
            category=category,
            healthy_only=True,
        )
        
        return [
            {
                "name": t.name,
                "description": t.schema.get("description", ""),
                "parameters": t.schema.get("parameters", {}),
                "category": t.category,
            }
            for t in tools
        ]
    
    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Execute a tool with given arguments.
        
        MCP Protocol: tools/call
        
        Args:
            name: Tool name
            arguments: Tool parameters
        
        Returns:
            Result dict with content or error
        """
        try:
            result = await self.registry.execute(name, arguments)
            return {
                "content": [
                    {"type": "text", "text": str(result)}
                ],
                "isError": False,
            }
        except Exception as exc:
            logger.error("Tool execution failed: %s", exc)
            return {
                "content": [
                    {"type": "text", "text": f"Error: {exc}"}
                ],
                "isError": True,
            }
    
    def get_schema(self, name: str) -> Optional[dict]:
        """Get the JSON schema for a tool.
        
        MCP Protocol: tools/schema
        """
        return self.registry.get_schema(name)
    
    def get_tool_info(self, name: str) -> Optional[dict]:
        """Get detailed info about a tool including health metrics."""
        record = self.registry.get(name)
        if not record:
            return None
        
        return {
            "name": record.name,
            "schema": record.schema,
            "category": record.category,
            "health": record.health_status,
            "metrics": {
                "executions": record.execution_count,
                "errors": record.error_count,
                "avg_latency_ms": round(record.avg_latency_ms, 2),
            },
            "requires_confirmation": record.requires_confirmation,
        }
    
    def health_check(self) -> dict:
        """Server health status."""
        tools = self.registry.list_tools()
        healthy = sum(
            1 for t in tools
            if self.registry.check_health(t) == "healthy"
        )
        
        return {
            "status": "healthy",
            "total_tools": len(tools),
            "healthy_tools": healthy,
            "degraded_tools": sum(
                1 for t in tools
                if self.registry.check_health(t) == "degraded"
            ),
            "unhealthy_tools": sum(
                1 for t in tools
                if self.registry.check_health(t) == "unhealthy"
            ),
        }


class MCPHTTPServer:
    """HTTP API wrapper for MCP Server."""
    
    def __init__(self) -> None:
        self.mcp = MCPServer()
    
    def get_routes(self) -> dict:
        """Get FastAPI route handlers."""
        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel
        
        router = APIRouter(prefix="/mcp", tags=["mcp"])
        
        class ToolCallRequest(BaseModel):
            name: str
            arguments: dict = {}
        
        @router.get("/tools")
        async def list_tools(
            category: Optional[str] = None,
            query: Optional[str] = None,
        ):
            """List available tools."""
            return {"tools": self.mcp.list_tools(category, query)}
        
        @router.post("/tools/call")
        async def call_tool(request: ToolCallRequest):
            """Execute a tool."""
            result = await self.mcp.call_tool(request.name, request.arguments)
            return result
        
        @router.get("/tools/{name}")
        async def get_tool(name: str):
            """Get tool info."""
            info = self.mcp.get_tool_info(name)
            if not info:
                raise HTTPException(404, f"Tool '{name}' not found")
            return info
        
        @router.get("/tools/{name}/schema")
        async def get_schema(name: str):
            """Get tool schema."""
            schema = self.mcp.get_schema(name)
            if not schema:
                raise HTTPException(404, f"Tool '{name}' not found")
            return schema
        
        @router.get("/health")
        async def health():
            """Server health check."""
            return self.mcp.health_check()
        
        return router


# Module-level singleton
mcp_server = MCPServer()


# Convenience functions for agents
def discover_tools(query: Optional[str] = None) -> list[dict]:
    """Quick tool discovery."""
    return mcp_server.list_tools(query=query)


async def use_tool(name: str, **kwargs) -> str:
    """Execute a tool and return result text."""
    result = await mcp_server.call_tool(name, kwargs)
    
    if result.get("isError"):
        raise RuntimeError(result["content"][0]["text"])
    
    return result["content"][0]["text"]
