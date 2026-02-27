"""File operations tool.

MCP-compliant tool for reading, writing, and listing files.
"""

import logging
from pathlib import Path
from typing import Any

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, PARAM_STRING, PARAM_BOOLEAN, RETURN_STRING

logger = logging.getLogger(__name__)


# Read File Schema
READ_FILE_SCHEMA = create_tool_schema(
    name="read_file",
    description="Read contents of a file. Use when user explicitly asks to read a file.",
    parameters={
        "path": {
            **PARAM_STRING,
            "description": "Path to file (relative to project root or absolute)",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum lines to read (0 = all)",
            "default": 0,
        },
    },
    required=["path"],
    returns=RETURN_STRING,
)

# Write File Schema
WRITE_FILE_SCHEMA = create_tool_schema(
    name="write_file",
    description="Write content to a file. Use when user explicitly asks to save content.",
    parameters={
        "path": {
            **PARAM_STRING,
            "description": "Path to file",
        },
        "content": {
            **PARAM_STRING,
            "description": "Content to write",
        },
        "append": {
            **PARAM_BOOLEAN,
            "description": "Append to file instead of overwrite",
            "default": False,
        },
    },
    required=["path", "content"],
    returns=RETURN_STRING,
)

# List Directory Schema
LIST_DIR_SCHEMA = create_tool_schema(
    name="list_directory",
    description="List files in a directory.",
    parameters={
        "path": {
            **PARAM_STRING,
            "description": "Directory path (default: current)",
            "default": ".",
        },
        "pattern": {
            **PARAM_STRING,
            "description": "File pattern filter (e.g., '*.py')",
            "default": "*",
        },
    },
    returns=RETURN_STRING,
)


def _resolve_path(path: str) -> Path:
    """Resolve path relative to project root."""
    from config import settings
    
    p = Path(path)
    if p.is_absolute():
        return p
    
    # Try relative to project root
    project_root = Path(__file__).parent.parent.parent
    return project_root / p


def read_file(path: str, limit: int = 0) -> str:
    """Read file contents."""
    try:
        filepath = _resolve_path(path)
        
        if not filepath.exists():
            return f"Error: File not found: {path}"
        
        if not filepath.is_file():
            return f"Error: Path is not a file: {path}"
        
        content = filepath.read_text()
        
        if limit > 0:
            lines = content.split('\n')[:limit]
            content = '\n'.join(lines)
            if len(content.split('\n')) == limit:
                content += f"\n\n... [{limit} lines shown]"
        
        return content
        
    except Exception as exc:
        logger.error("Read file failed: %s", exc)
        return f"Error reading file: {exc}"


def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to file."""
    try:
        filepath = _resolve_path(path)
        
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "a" if append else "w"
        filepath.write_text(content)
        
        action = "appended to" if append else "wrote"
        return f"Successfully {action} {filepath}"
        
    except Exception as exc:
        logger.error("Write file failed: %s", exc)
        return f"Error writing file: {exc}"


def list_directory(path: str = ".", pattern: str = "*") -> str:
    """List directory contents."""
    try:
        dirpath = _resolve_path(path)
        
        if not dirpath.exists():
            return f"Error: Directory not found: {path}"
        
        if not dirpath.is_dir():
            return f"Error: Path is not a directory: {path}"
        
        items = list(dirpath.glob(pattern))
        
        files = []
        dirs = []
        
        for item in items:
            if item.is_dir():
                dirs.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
                files.append(f"📄 {item.name} ({size_str})")
        
        result = [f"Contents of {dirpath}:", ""]
        result.extend(sorted(dirs))
        result.extend(sorted(files))
        
        return "\n".join(result)
        
    except Exception as exc:
        logger.error("List directory failed: %s", exc)
        return f"Error listing directory: {exc}"


# Register with MCP
register_tool(name="read_file", schema=READ_FILE_SCHEMA, category="files")(read_file)
register_tool(
    name="write_file",
    schema=WRITE_FILE_SCHEMA,
    category="files",
    requires_confirmation=True,
)(write_file)
register_tool(name="list_directory", schema=LIST_DIR_SCHEMA, category="files")(list_directory)
