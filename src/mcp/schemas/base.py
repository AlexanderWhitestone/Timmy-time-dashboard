"""Base schemas for MCP (Model Context Protocol) tools.

All tools must provide a JSON schema describing their interface.
This enables dynamic discovery and type-safe invocation.
"""

from typing import Any


def create_tool_schema(
    name: str,
    description: str,
    parameters: dict[str, Any],
    required: list[str] | None = None,
    returns: dict[str, Any] | None = None,
) -> dict:
    """Create a standard MCP tool schema.
    
    Args:
        name: Tool name (must be unique)
        description: Human-readable description
        parameters: JSON schema for input parameters
        required: List of required parameter names
        returns: JSON schema for return value
    
    Returns:
        Complete tool schema dict
    """
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": required or [],
        },
        "returns": returns or {"type": "string"},
    }


# Common parameter schemas
PARAM_STRING = {"type": "string"}
PARAM_INTEGER = {"type": "integer"}
PARAM_BOOLEAN = {"type": "boolean"}
PARAM_ARRAY_STRINGS = {"type": "array", "items": {"type": "string"}}
PARAM_OBJECT = {"type": "object"}

# Common return schemas
RETURN_STRING = {"type": "string"}
RETURN_OBJECT = {"type": "object"}
RETURN_ARRAY = {"type": "array"}
RETURN_BOOLEAN = {"type": "boolean"}
