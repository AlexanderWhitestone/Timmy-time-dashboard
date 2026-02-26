"""MCP (Model Context Protocol) package.

Provides tool registry, server, and schema management.
"""

from mcp.registry import tool_registry, register_tool
from mcp.server import mcp_server, MCPServer, MCPHTTPServer
from mcp.schemas.base import create_tool_schema

__all__ = [
    "tool_registry",
    "register_tool",
    "mcp_server",
    "MCPServer",
    "MCPHTTPServer",
    "create_tool_schema",
]
