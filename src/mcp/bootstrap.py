"""Bootstrap the MCP system by loading all tools.

This module is responsible for:
1. Loading all tool modules from src/tools/
2. Registering them with the tool registry
3. Verifying tool health
4. Reporting status
"""

import importlib
import logging
from pathlib import Path

from mcp.registry import tool_registry

logger = logging.getLogger(__name__)

# Tool modules to load
TOOL_MODULES = [
    "tools.web_search",
    "tools.file_ops",
    "tools.code_exec",
    "tools.memory_tool",
]


def bootstrap_mcp() -> dict:
    """Initialize the MCP system by loading all tools.
    
    Returns:
        Status dict with loaded tools and any errors
    """
    loaded = []
    errors = []
    
    for module_name in TOOL_MODULES:
        try:
            # Import the module (this triggers @register_tool decorators)
            importlib.import_module(module_name)
            loaded.append(module_name)
            logger.info("Loaded tool module: %s", module_name)
        except Exception as exc:
            errors.append({"module": module_name, "error": str(exc)})
            logger.error("Failed to load tool module %s: %s", module_name, exc)
    
    # Get registry status
    registry_status = tool_registry.to_dict()
    
    status = {
        "loaded_modules": loaded,
        "errors": errors,
        "total_tools": len(registry_status.get("tools", [])),
        "tools_by_category": registry_status.get("categories", {}),
        "tool_names": tool_registry.list_tools(),
    }
    
    logger.info(
        "MCP Bootstrap complete: %d tools loaded from %d modules",
        status["total_tools"],
        len(loaded)
    )
    
    return status


def get_tool_status() -> dict:
    """Get current status of all tools."""
    return {
        "tools": tool_registry.to_dict(),
        "metrics": tool_registry.get_metrics(),
    }
