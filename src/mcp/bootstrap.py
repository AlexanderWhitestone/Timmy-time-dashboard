"""MCP Auto-Bootstrap — Auto-discover and register tools on startup.

Usage:
    from mcp.bootstrap import auto_bootstrap
    
    # Auto-discover from 'tools' package
    registered = auto_bootstrap()
    
    # Or specify custom packages
    registered = auto_bootstrap(packages=["tools", "custom_tools"])
"""

import logging
import os
from pathlib import Path
from typing import Optional

from .discovery import ToolDiscovery, get_discovery
from .registry import ToolRegistry, tool_registry

logger = logging.getLogger(__name__)

# Default packages to scan for tools
DEFAULT_TOOL_PACKAGES = ["tools"]

# Environment variable to disable auto-bootstrap
AUTO_BOOTSTRAP_ENV_VAR = "MCP_AUTO_BOOTSTRAP"


def auto_bootstrap(
    packages: Optional[list[str]] = None,
    registry: Optional[ToolRegistry] = None,
    force: bool = False,
) -> list[str]:
    """Auto-discover and register MCP tools.
    
    Args:
        packages: Packages to scan (defaults to ["tools"])
        registry: Registry to register tools with (defaults to singleton)
        force: Force bootstrap even if disabled by env var
    
    Returns:
        List of registered tool names
    """
    # Check if auto-bootstrap is disabled
    if not force and os.environ.get(AUTO_BOOTSTRAP_ENV_VAR, "1") == "0":
        logger.info("MCP auto-bootstrap disabled via %s", AUTO_BOOTSTRAP_ENV_VAR)
        return []
    
    packages = packages or DEFAULT_TOOL_PACKAGES
    registry = registry or tool_registry
    discovery = get_discovery(registry=registry)
    
    registered: list[str] = []
    
    logger.info("Starting MCP auto-bootstrap from packages: %s", packages)
    
    for package in packages:
        try:
            # Check if package exists
            try:
                __import__(package)
            except ImportError:
                logger.debug("Package %s not found, skipping", package)
                continue
            
            # Discover and register
            tools = discovery.auto_register(package)
            registered.extend(tools)
            
        except Exception as exc:
            logger.warning("Failed to bootstrap from %s: %s", package, exc)
    
    logger.info("MCP auto-bootstrap complete: %d tools registered", len(registered))
    return registered


def bootstrap_from_directory(
    directory: Path,
    registry: Optional[ToolRegistry] = None,
) -> list[str]:
    """Bootstrap tools from a directory of Python files.
    
    Args:
        directory: Directory containing Python files with tools
        registry: Registry to register tools with
    
    Returns:
        List of registered tool names
    """
    registry = registry or tool_registry
    discovery = get_discovery(registry=registry)
    
    registered: list[str] = []
    
    if not directory.exists():
        logger.warning("Tools directory not found: %s", directory)
        return registered
    
    logger.info("Bootstrapping tools from directory: %s", directory)
    
    # Find all Python files
    for py_file in directory.rglob("*.py"):
        if py_file.name.startswith("_"):
            continue
        
        try:
            discovered = discovery.discover_file(py_file)
            
            for tool in discovered:
                if tool.function is None:
                    # Need to import and resolve the function
                    continue
                
                try:
                    registry.register_tool(
                        name=tool.name,
                        function=tool.function,
                        description=tool.description,
                        category=tool.category,
                        tags=tool.tags,
                    )
                    registered.append(tool.name)
                except Exception as exc:
                    logger.error("Failed to register %s: %s", tool.name, exc)
                    
        except Exception as exc:
            logger.warning("Failed to process %s: %s", py_file, exc)
    
    logger.info("Directory bootstrap complete: %d tools registered", len(registered))
    return registered


def get_bootstrap_status() -> dict:
    """Get auto-bootstrap status.
    
    Returns:
        Dict with bootstrap status info
    """
    discovery = get_discovery()
    registry = tool_registry
    
    return {
        "auto_bootstrap_enabled": os.environ.get(AUTO_BOOTSTRAP_ENV_VAR, "1") != "0",
        "discovered_tools_count": len(discovery.get_discovered()),
        "registered_tools_count": len(registry.list_tools()),
        "default_packages": DEFAULT_TOOL_PACKAGES,
    }
