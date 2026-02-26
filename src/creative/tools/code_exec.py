"""Code execution tool.

MCP-compliant tool for executing Python code.
"""

import logging
import traceback
from typing import Any

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, PARAM_STRING, PARAM_BOOLEAN, RETURN_STRING

logger = logging.getLogger(__name__)


PYTHON_SCHEMA = create_tool_schema(
    name="python",
    description="Execute Python code. Use for calculations, data processing, or when precise computation is needed. Code runs in a restricted environment.",
    parameters={
        "code": {
            **PARAM_STRING,
            "description": "Python code to execute",
        },
        "return_output": {
            **PARAM_BOOLEAN,
            "description": "Return the value of the last expression",
            "default": True,
        },
    },
    required=["code"],
    returns=RETURN_STRING,
)


def python(code: str, return_output: bool = True) -> str:
    """Execute Python code in restricted environment.
    
    Args:
        code: Python code to execute
        return_output: Whether to return last expression value
    
    Returns:
        Execution result or error message
    """
    # Safe globals for code execution
    safe_globals = {
        "__builtins__": {
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "print": lambda *args, **kwargs: None,  # Disabled
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "zip": zip,
        }
    }
    
    # Allowed modules
    allowed_modules = ["math", "random", "statistics", "datetime", "json"]
    
    for mod_name in allowed_modules:
        try:
            safe_globals[mod_name] = __import__(mod_name)
        except ImportError:
            pass
    
    try:
        # Compile and execute
        compiled = compile(code, "<string>", "eval" if return_output else "exec")
        
        if return_output:
            result = eval(compiled, safe_globals, {})
            return f"Result: {result}"
        else:
            exec(compiled, safe_globals, {})
            return "Code executed successfully."
            
    except SyntaxError:
        # Try as exec if eval fails
        try:
            compiled = compile(code, "<string>", "exec")
            exec(compiled, safe_globals, {})
            return "Code executed successfully."
        except Exception as exc:
            error_msg = traceback.format_exc()
            logger.error("Python execution failed: %s", exc)
            return f"Error: {exc}\n\n{error_msg}"
    except Exception as exc:
        error_msg = traceback.format_exc()
        logger.error("Python execution failed: %s", exc)
        return f"Error: {exc}\n\n{error_msg}"


# Register with MCP
register_tool(name="python", schema=PYTHON_SCHEMA, category="code")(python)
