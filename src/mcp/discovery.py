"""MCP Tool Auto-Discovery — Introspect Python modules to find tools.

Automatically discovers functions marked with @mcp_tool decorator
and registers them with the MCP registry. Generates JSON schemas
from type hints.
"""

import ast
import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, get_type_hints

from .registry import ToolRegistry, tool_registry

logger = logging.getLogger(__name__)


# Decorator to mark functions as MCP tools
def mcp_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "general",
    tags: Optional[list[str]] = None,
):
    """Decorator to mark a function as an MCP tool.
    
    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        category: Tool category for organization
        tags: Additional tags for filtering
    
    Example:
        @mcp_tool(name="weather", category="external")
        def get_weather(city: str) -> dict:
            '''Get weather for a city.'''
            ...
    """
    def decorator(func: Callable) -> Callable:
        func._mcp_tool = True
        func._mcp_name = name or func.__name__
        func._mcp_description = description or (func.__doc__ or "").strip()
        func._mcp_category = category
        func._mcp_tags = tags or []
        return func
    return decorator


@dataclass
class DiscoveredTool:
    """A tool discovered via introspection."""
    name: str
    description: str
    function: Callable
    module: str
    category: str
    tags: list[str]
    parameters_schema: dict[str, Any]
    returns_schema: dict[str, Any]
    source_file: Optional[str] = None
    line_number: int = 0


class ToolDiscovery:
    """Discovers and registers MCP tools from Python modules.
    
    Usage:
        discovery = ToolDiscovery()
        
        # Discover from a module
        tools = discovery.discover_module("creative.tools.git")

        # Auto-register with registry
        discovery.auto_register("creative.tools")
        
        # Discover from all installed packages
        tools = discovery.discover_all_packages()
    """
    
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or tool_registry
        self._discovered: list[DiscoveredTool] = []
    
    def discover_module(self, module_name: str) -> list[DiscoveredTool]:
        """Discover all MCP tools in a module.
        
        Args:
            module_name: Dotted path to module (e.g., "creative.tools.git")
        
        Returns:
            List of discovered tools
        """
        discovered = []
        
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning("Failed to import module %s: %s", module_name, exc)
            return discovered
        
        # Get module file path for source location
        module_file = getattr(module, "__file__", None)
        
        # Iterate through module members
        for name, obj in inspect.getmembers(module):
            # Skip private and non-callable
            if name.startswith("_") or not callable(obj):
                continue
            
            # Check if marked as MCP tool
            if not getattr(obj, "_mcp_tool", False):
                continue
            
            # Get source location
            try:
                source_file = inspect.getfile(obj)
                line_number = inspect.getsourcelines(obj)[1]
            except (OSError, TypeError):
                source_file = module_file
                line_number = 0
            
            # Build schemas from type hints
            try:
                sig = inspect.signature(obj)
                parameters_schema = self._build_parameters_schema(sig)
                returns_schema = self._build_returns_schema(sig, obj)
            except Exception as exc:
                logger.warning("Failed to build schema for %s: %s", name, exc)
                parameters_schema = {"type": "object", "properties": {}}
                returns_schema = {}
            
            tool = DiscoveredTool(
                name=getattr(obj, "_mcp_name", name),
                description=getattr(obj, "_mcp_description", obj.__doc__ or ""),
                function=obj,
                module=module_name,
                category=getattr(obj, "_mcp_category", "general"),
                tags=getattr(obj, "_mcp_tags", []),
                parameters_schema=parameters_schema,
                returns_schema=returns_schema,
                source_file=source_file,
                line_number=line_number,
            )
            
            discovered.append(tool)
            logger.debug("Discovered tool: %s from %s", tool.name, module_name)
        
        self._discovered.extend(discovered)
        logger.info("Discovered %d tools from module %s", len(discovered), module_name)
        return discovered
    
    def discover_package(self, package_name: str, recursive: bool = True) -> list[DiscoveredTool]:
        """Discover tools from all modules in a package.
        
        Args:
            package_name: Package name (e.g., "tools")
            recursive: Whether to search subpackages
        
        Returns:
            List of discovered tools
        """
        discovered = []
        
        try:
            package = importlib.import_module(package_name)
        except ImportError as exc:
            logger.warning("Failed to import package %s: %s", package_name, exc)
            return discovered
        
        package_path = getattr(package, "__path__", [])
        if not package_path:
            # Not a package, treat as module
            return self.discover_module(package_name)
        
        # Walk package modules
        for _, name, is_pkg in pkgutil.iter_modules(package_path, prefix=f"{package_name}."):
            if is_pkg and recursive:
                discovered.extend(self.discover_package(name, recursive=True))
            else:
                discovered.extend(self.discover_module(name))
        
        return discovered
    
    def discover_file(self, file_path: Path) -> list[DiscoveredTool]:
        """Discover tools from a Python file.
        
        Args:
            file_path: Path to Python file
        
        Returns:
            List of discovered tools
        """
        discovered = []
        
        try:
            source = file_path.read_text()
            tree = ast.parse(source)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path, exc)
            return discovered
        
        # Find all decorated functions
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            
            # Check for @mcp_tool decorator
            is_tool = False
            tool_name = node.name
            tool_description = ast.get_docstring(node) or ""
            tool_category = "general"
            tool_tags: list[str] = []
            
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name) and decorator.func.id == "mcp_tool":
                        is_tool = True
                        # Extract decorator arguments
                        for kw in decorator.keywords:
                            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                                tool_name = kw.value.value
                            elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                                tool_description = kw.value.value
                            elif kw.arg == "category" and isinstance(kw.value, ast.Constant):
                                tool_category = kw.value.value
                            elif kw.arg == "tags" and isinstance(kw.value, ast.List):
                                tool_tags = [
                                    elt.value for elt in kw.value.elts
                                    if isinstance(elt, ast.Constant)
                                ]
                elif isinstance(decorator, ast.Name) and decorator.id == "mcp_tool":
                    is_tool = True
            
            if not is_tool:
                continue
            
            # Build parameter schema from AST
            parameters_schema = self._build_schema_from_ast(node)
            
            # We can't get the actual function without importing
            # So create a placeholder that will be resolved later
            tool = DiscoveredTool(
                name=tool_name,
                description=tool_description,
                function=None,  # Will be resolved when registered
                module=str(file_path),
                category=tool_category,
                tags=tool_tags,
                parameters_schema=parameters_schema,
                returns_schema={"type": "object"},
                source_file=str(file_path),
                line_number=node.lineno,
            )
            
            discovered.append(tool)
        
        self._discovered.extend(discovered)
        logger.info("Discovered %d tools from file %s", len(discovered), file_path)
        return discovered
    
    def auto_register(self, package_name: str = "tools") -> list[str]:
        """Automatically discover and register tools.
        
        Args:
            package_name: Package to scan for tools
        
        Returns:
            List of registered tool names
        """
        discovered = self.discover_package(package_name)
        registered = []
        
        for tool in discovered:
            if tool.function is None:
                logger.warning("Skipping %s: no function resolved", tool.name)
                continue
            
            try:
                self.registry.register_tool(
                    name=tool.name,
                    function=tool.function,
                    description=tool.description,
                    category=tool.category,
                    tags=tool.tags,
                )
                registered.append(tool.name)
                logger.debug("Registered tool: %s", tool.name)
            except Exception as exc:
                logger.error("Failed to register %s: %s", tool.name, exc)
        
        logger.info("Auto-registered %d/%d tools", len(registered), len(discovered))
        return registered
    
    def _build_parameters_schema(self, sig: inspect.Signature) -> dict[str, Any]:
        """Build JSON schema for function parameters."""
        properties = {}
        required = []
        
        for name, param in sig.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            
            schema = self._type_to_schema(param.annotation)
            
            if param.default is param.empty:
                required.append(name)
            else:
                schema["default"] = param.default
            
            properties[name] = schema
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    def _build_returns_schema(
        self, sig: inspect.Signature, func: Callable
    ) -> dict[str, Any]:
        """Build JSON schema for return type."""
        return_annotation = sig.return_annotation
        
        if return_annotation is sig.empty:
            return {"type": "object"}
        
        return self._type_to_schema(return_annotation)
    
    def _build_schema_from_ast(self, node: ast.FunctionDef) -> dict[str, Any]:
        """Build parameter schema from AST node."""
        properties = {}
        required = []
        
        # Get defaults (reversed, since they're at the end)
        defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
        
        for arg, default in zip(node.args.args, defaults):
            arg_name = arg.arg
            arg_type = "string"  # Default
            
            # Try to get type from annotation
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    arg_type = self._ast_type_to_json_type(arg.annotation.id)
                elif isinstance(arg.annotation, ast.Constant):
                    arg_type = self._ast_type_to_json_type(str(arg.annotation.value))
            
            schema = {"type": arg_type}
            
            if default is None:
                required.append(arg_name)
            
            properties[arg_name] = schema
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    def _type_to_schema(self, annotation: Any) -> dict[str, Any]:
        """Convert Python type annotation to JSON schema."""
        if annotation is inspect.Parameter.empty:
            return {"type": "string"}
        
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        
        # Handle Optional[T] = Union[T, None]
        if origin is not None:
            if str(origin) == "typing.Union" and type(None) in args:
                # Optional type
                non_none_args = [a for a in args if a is not type(None)]
                if len(non_none_args) == 1:
                    schema = self._type_to_schema(non_none_args[0])
                    return schema
                return {"type": "object"}
            
            # Handle List[T], Dict[K,V]
            if origin in (list, tuple):
                items_schema = {"type": "object"}
                if args:
                    items_schema = self._type_to_schema(args[0])
                return {"type": "array", "items": items_schema}
            
            if origin is dict:
                return {"type": "object"}
        
        # Handle basic types
        if annotation in (str,):
            return {"type": "string"}
        elif annotation in (int, float):
            return {"type": "number"}
        elif annotation in (bool,):
            return {"type": "boolean"}
        elif annotation in (list, tuple):
            return {"type": "array"}
        elif annotation in (dict,):
            return {"type": "object"}
        
        return {"type": "object"}
    
    def _ast_type_to_json_type(self, type_name: str) -> str:
        """Convert AST type name to JSON schema type."""
        type_map = {
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "List": "array",
            "Dict": "object",
            "Optional": "object",
            "Any": "object",
        }
        return type_map.get(type_name, "object")
    
    def get_discovered(self) -> list[DiscoveredTool]:
        """Get all discovered tools."""
        return list(self._discovered)
    
    def clear(self) -> None:
        """Clear discovered tools cache."""
        self._discovered.clear()


# Module-level singleton
discovery: Optional[ToolDiscovery] = None


def get_discovery(registry: Optional[ToolRegistry] = None) -> ToolDiscovery:
    """Get or create the tool discovery singleton."""
    global discovery
    if discovery is None:
        discovery = ToolDiscovery(registry=registry)
    return discovery
