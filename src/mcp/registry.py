"""MCP Tool Registry — Dynamic tool discovery and management.

The registry maintains a catalog of all available tools, their schemas,
and health status. Tools can be registered dynamically at runtime.

Usage:
    from mcp.registry import tool_registry
    
    # Register a tool
    tool_registry.register("web_search", web_search_schema, web_search_func)
    
    # Discover tools
    tools = tool_registry.discover(capabilities=["search"])
    
    # Execute a tool
    result = tool_registry.execute("web_search", {"query": "Bitcoin"})
"""

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from mcp.schemas.base import create_tool_schema

logger = logging.getLogger(__name__)


@dataclass
class ToolRecord:
    """A registered tool with metadata."""
    name: str
    schema: dict
    handler: Callable
    category: str = "general"
    health_status: str = "unknown"  # healthy, degraded, unhealthy
    last_execution: Optional[float] = None
    execution_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    added_at: float = field(default_factory=time.time)
    requires_confirmation: bool = False


class ToolRegistry:
    """Central registry for all MCP tools."""
    
    def __init__(self) -> None:
        self._tools: dict[str, ToolRecord] = {}
        self._categories: dict[str, list[str]] = {}
        logger.info("ToolRegistry initialized")
    
    def register(
        self,
        name: str,
        schema: dict,
        handler: Callable,
        category: str = "general",
        requires_confirmation: bool = False,
    ) -> ToolRecord:
        """Register a new tool.
        
        Args:
            name: Unique tool name
            schema: JSON schema describing inputs/outputs
            handler: Function to execute
            category: Tool category for organization
            requires_confirmation: If True, user must approve before execution
        
        Returns:
            The registered ToolRecord
        """
        if name in self._tools:
            logger.warning("Tool '%s' already registered, replacing", name)
        
        record = ToolRecord(
            name=name,
            schema=schema,
            handler=handler,
            category=category,
            requires_confirmation=requires_confirmation,
        )
        
        self._tools[name] = record
        
        # Add to category
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)
        
        logger.info("Registered tool: %s (category: %s)", name, category)
        return record
    
    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name not in self._tools:
            return False
        
        record = self._tools.pop(name)
        
        # Remove from category
        if record.category in self._categories:
            if name in self._categories[record.category]:
                self._categories[record.category].remove(name)
        
        logger.info("Unregistered tool: %s", name)
        return True
    
    def get(self, name: str) -> Optional[ToolRecord]:
        """Get a tool record by name."""
        return self._tools.get(name)
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """Get just the handler function for a tool."""
        record = self._tools.get(name)
        return record.handler if record else None
    
    def get_schema(self, name: str) -> Optional[dict]:
        """Get the JSON schema for a tool."""
        record = self._tools.get(name)
        return record.schema if record else None
    
    def list_tools(self, category: Optional[str] = None) -> list[str]:
        """List all tool names, optionally filtered by category."""
        if category:
            return self._categories.get(category, [])
        return list(self._tools.keys())
    
    def list_categories(self) -> list[str]:
        """List all tool categories."""
        return list(self._categories.keys())
    
    def discover(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        healthy_only: bool = True,
    ) -> list[ToolRecord]:
        """Discover tools matching criteria.
        
        Args:
            query: Search in tool names and descriptions
            category: Filter by category
            healthy_only: Only return healthy tools
        
        Returns:
            List of matching ToolRecords
        """
        results = []
        
        for name, record in self._tools.items():
            # Category filter
            if category and record.category != category:
                continue
            
            # Health filter
            if healthy_only and record.health_status == "unhealthy":
                continue
            
            # Query filter
            if query:
                query_lower = query.lower()
                name_match = query_lower in name.lower()
                desc = record.schema.get("description", "")
                desc_match = query_lower in desc.lower()
                if not (name_match or desc_match):
                    continue
            
            results.append(record)
        
        return results
    
    async def execute(self, name: str, params: dict) -> Any:
        """Execute a tool by name with given parameters.
        
        Args:
            name: Tool name
            params: Parameters to pass to the tool
        
        Returns:
            Tool execution result
        
        Raises:
            ValueError: If tool not found
            RuntimeError: If tool execution fails
        """
        record = self._tools.get(name)
        if not record:
            raise ValueError(f"Tool '{name}' not found in registry")
        
        start_time = time.time()
        
        try:
            # Check if handler is async
            if inspect.iscoroutinefunction(record.handler):
                result = await record.handler(**params)
            else:
                result = record.handler(**params)
            
            # Update metrics
            latency_ms = (time.time() - start_time) * 1000
            record.last_execution = time.time()
            record.execution_count += 1
            
            # Update rolling average latency
            if record.execution_count == 1:
                record.avg_latency_ms = latency_ms
            else:
                record.avg_latency_ms = (
                    record.avg_latency_ms * 0.9 + latency_ms * 0.1
                )
            
            # Mark healthy on success
            record.health_status = "healthy"
            
            logger.debug("Tool '%s' executed in %.2fms", name, latency_ms)
            return result
            
        except Exception as exc:
            record.error_count += 1
            record.execution_count += 1
            
            # Degrade health on repeated errors
            error_rate = record.error_count / record.execution_count
            if error_rate > 0.5:
                record.health_status = "unhealthy"
                logger.error("Tool '%s' marked unhealthy (error rate: %.1f%%)", 
                           name, error_rate * 100)
            elif error_rate > 0.2:
                record.health_status = "degraded"
                logger.warning("Tool '%s' degraded (error rate: %.1f%%)", 
                             name, error_rate * 100)
            
            raise RuntimeError(f"Tool '{name}' execution failed: {exc}") from exc
    
    def check_health(self, name: str) -> str:
        """Check health status of a tool."""
        record = self._tools.get(name)
        if not record:
            return "not_found"
        return record.health_status
    
    def get_metrics(self, name: Optional[str] = None) -> dict:
        """Get metrics for a tool or all tools."""
        if name:
            record = self._tools.get(name)
            if not record:
                return {}
            return {
                "name": record.name,
                "category": record.category,
                "health": record.health_status,
                "executions": record.execution_count,
                "errors": record.error_count,
                "avg_latency_ms": round(record.avg_latency_ms, 2),
            }
        
        # Return metrics for all tools
        return {
            name: self.get_metrics(name)
            for name in self._tools.keys()
        }
    
    def to_dict(self) -> dict:
        """Export registry as dictionary (for API/dashboard)."""
        return {
            "tools": [
                {
                    "name": r.name,
                    "schema": r.schema,
                    "category": r.category,
                    "health": r.health_status,
                    "requires_confirmation": r.requires_confirmation,
                }
                for r in self._tools.values()
            ],
            "categories": self._categories,
            "total_tools": len(self._tools),
        }


# Module-level singleton
tool_registry = ToolRegistry()


def register_tool(
    name: Optional[str] = None,
    category: str = "general",
    schema: Optional[dict] = None,
    requires_confirmation: bool = False,
):
    """Decorator for registering a function as an MCP tool.
    
    Usage:
        @register_tool(name="web_search", category="research")
        def web_search(query: str, max_results: int = 5) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        
        # Auto-generate schema if not provided
        if schema is None:
            # Try to infer from type hints
            sig = inspect.signature(func)
            params = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                    params[param_name] = {"type": "string"}
                else:
                    params[param_name] = {
                        "type": "string",
                        "default": str(param.default),
                    }
            
            tool_schema = create_tool_schema(
                name=tool_name,
                description=func.__doc__ or f"Execute {tool_name}",
                parameters=params,
                required=required,
            )
        else:
            tool_schema = schema
        
        tool_registry.register(
            name=tool_name,
            schema=tool_schema,
            handler=func,
            category=category,
            requires_confirmation=requires_confirmation,
        )
        
        return func
    return decorator
