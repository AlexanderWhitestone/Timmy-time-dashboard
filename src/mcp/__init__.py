"""MCP (Model Context Protocol) package.

Provides tool registry, server, schema management, and auto-discovery.
"""

from mcp.registry import tool_registry, register_tool, ToolRegistry
from mcp.server import mcp_server, MCPServer, MCPHTTPServer
from mcp.schemas.base import create_tool_schema
from mcp.discovery import ToolDiscovery, mcp_tool, get_discovery
from mcp.bootstrap import auto_bootstrap, get_bootstrap_status

__all__ = [
    # Registry
    "tool_registry",
    "register_tool",
    "ToolRegistry",
    # Server
    "mcp_server",
    "MCPServer",
    "MCPHTTPServer",
    # Schemas
    "create_tool_schema",
    # Discovery
    "ToolDiscovery",
    "mcp_tool",
    "get_discovery",
    # Bootstrap
    "auto_bootstrap",
    "get_bootstrap_status",
]
