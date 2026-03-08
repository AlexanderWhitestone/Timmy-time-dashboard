"""Tool integration for the agent swarm.

Provides agents with capabilities for:
- Web search (DuckDuckGo)
- File read/write (local filesystem)
- Shell command execution (sandboxed)
- Python code execution
- Git operations
- Image / Music / Video generation (creative pipeline)

Tools are assigned to agents based on their specialties.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Lazy imports to handle test mocking
_ImportError = None
try:
    from agno.tools import Toolkit
    from agno.tools.duckduckgo import DuckDuckGoTools
    from agno.tools.file import FileTools
    from agno.tools.python import PythonTools
    from agno.tools.shell import ShellTools

    _AGNO_TOOLS_AVAILABLE = True
except ImportError as e:
    _AGNO_TOOLS_AVAILABLE = False
    _ImportError = e

# Track tool usage stats
_TOOL_USAGE: dict[str, list[dict]] = {}


@dataclass
class ToolStats:
    """Statistics for a single tool."""

    tool_name: str
    call_count: int = 0
    last_used: str | None = None
    errors: int = 0


@dataclass
class AgentTools:
    """Tools assigned to an agent."""

    agent_id: str
    agent_name: str
    toolkit: Toolkit
    available_tools: list[str] = field(default_factory=list)


# Backward-compat alias
PersonaTools = AgentTools


def _track_tool_usage(agent_id: str, tool_name: str, success: bool = True) -> None:
    """Track tool usage for analytics."""
    if agent_id not in _TOOL_USAGE:
        _TOOL_USAGE[agent_id] = []
    _TOOL_USAGE[agent_id].append(
        {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
        }
    )


def get_tool_stats(agent_id: str | None = None) -> dict:
    """Get tool usage statistics.

    Args:
        agent_id: Optional agent ID to filter by. If None, returns stats for all agents.

    Returns:
        Dict with tool usage statistics.
    """
    if agent_id:
        usage = _TOOL_USAGE.get(agent_id, [])
        return {
            "agent_id": agent_id,
            "total_calls": len(usage),
            "tools_used": list(set(u["tool"] for u in usage)),
            "recent_calls": usage[-10:] if usage else [],
        }

    # Return stats for all agents
    all_stats = {}
    for aid, usage in _TOOL_USAGE.items():
        all_stats[aid] = {
            "total_calls": len(usage),
            "tools_used": list(set(u["tool"] for u in usage)),
        }
    return all_stats


def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the exact result.

    Use this tool for ANY arithmetic: multiplication, division, square roots,
    exponents, percentages, logarithms, trigonometry, etc.

    Args:
        expression: A valid Python math expression, e.g. '347 * 829',
                    'math.sqrt(17161)', '2**10', 'math.log(100, 10)'.

    Returns:
        The exact result as a string.
    """
    # Only expose math functions — no builtins, no file/os access
    allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed_names["math"] = math  # Support math.sqrt(), math.pi, etc.
    allowed_names["abs"] = abs
    allowed_names["round"] = round
    allowed_names["min"] = min
    allowed_names["max"] = max
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"


def create_research_tools(base_dir: str | Path | None = None):
    """Create tools for the research agent (Echo).

    Includes: web search, file reading
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="research")

    # Web search via DuckDuckGo
    search_tools = DuckDuckGoTools()
    toolkit.register(search_tools.web_search, name="web_search")

    # File reading
    from config import settings

    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.list_files, name="list_files")

    return toolkit


def create_code_tools(base_dir: str | Path | None = None):
    """Create tools for the code agent (Forge).

    Includes: shell commands, python execution, file read/write, Aider AI assist
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="code")

    # Shell commands (sandboxed)
    shell_tools = ShellTools()
    toolkit.register(shell_tools.run_shell_command, name="shell")

    # Python execution
    python_tools = PythonTools()
    toolkit.register(python_tools.run_python_code, name="python")

    # File operations
    from config import settings

    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.save_file, name="write_file")
    toolkit.register(file_tools.list_files, name="list_files")

    # Aider AI coding assistant (local with Ollama)
    aider_tool = create_aider_tool(base_path)
    toolkit.register(aider_tool.run_aider, name="aider")

    return toolkit


def create_aider_tool(base_path: Path):
    """Create an Aider tool for AI-assisted coding."""
    import subprocess

    class AiderTool:
        """Tool that calls Aider (local AI coding assistant) for code generation."""

        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

        def run_aider(self, prompt: str, model: str = "qwen2.5:14b") -> str:
            """Run Aider to generate code changes.

            Args:
                prompt: What you want Aider to do (e.g., "add a fibonacci function")
                model: Ollama model to use (default: qwen2.5:14b)

            Returns:
                Aider's response with the code changes made
            """
            try:
                # Run aider with the prompt
                result = subprocess.run(
                    [
                        "aider",
                        "--no-git",
                        "--model",
                        f"ollama/{model}",
                        "--quiet",
                        prompt,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(self.base_dir),
                )

                if result.returncode == 0:
                    return (
                        result.stdout
                        if result.stdout
                        else "Code changes applied successfully"
                    )
                else:
                    return f"Aider error: {result.stderr}"
            except FileNotFoundError:
                return "Error: Aider not installed. Run: pip install aider"
            except subprocess.TimeoutExpired:
                return "Error: Aider timed out after 120 seconds"
            except Exception as e:
                return f"Error running Aider: {str(e)}"

    return AiderTool(base_path)


def create_data_tools(base_dir: str | Path | None = None):
    """Create tools for the data agent (Seer).

    Includes: python execution, file reading, web search for data sources
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="data")

    # Python execution for analysis
    python_tools = PythonTools()
    toolkit.register(python_tools.run_python_code, name="python")

    # File reading
    from config import settings

    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.list_files, name="list_files")

    # Web search for finding datasets
    search_tools = DuckDuckGoTools()
    toolkit.register(search_tools.web_search, name="web_search")

    return toolkit


def create_writing_tools(base_dir: str | Path | None = None):
    """Create tools for the writing agent (Quill).

    Includes: file read/write
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="writing")

    # File operations
    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.save_file, name="write_file")
    toolkit.register(file_tools.list_files, name="list_files")

    return toolkit


def create_security_tools(base_dir: str | Path | None = None):
    """Create tools for the security agent (Mace).

    Includes: shell commands (for scanning), web search (for threat intel), file read
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="security")

    # Shell for running security scans
    shell_tools = ShellTools()
    toolkit.register(shell_tools.run_shell_command, name="shell")

    # Web search for threat intelligence
    search_tools = DuckDuckGoTools()
    toolkit.register(search_tools.web_search, name="web_search")

    # File reading for logs/configs
    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.list_files, name="list_files")

    return toolkit


def create_devops_tools(base_dir: str | Path | None = None):
    """Create tools for the DevOps agent (Helm).

    Includes: shell commands, file read/write
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="devops")

    # Shell for deployment commands
    shell_tools = ShellTools()
    toolkit.register(shell_tools.run_shell_command, name="shell")

    # File operations for config management
    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.save_file, name="write_file")
    toolkit.register(file_tools.list_files, name="list_files")

    return toolkit


def consult_grok(query: str) -> str:
    """Consult Grok (xAI) for frontier reasoning on complex questions.

    Use this tool when a question requires advanced reasoning, real-time
    knowledge, or capabilities beyond the local model. Grok is a premium
    cloud backend — use sparingly and only for high-complexity queries.

    Args:
        query: The question or reasoning task to send to Grok.

    Returns:
        Grok's response text, or an error/status message.
    """
    from config import settings
    from timmy.backends import grok_available, get_grok_backend

    if not grok_available():
        return (
            "Grok is not available. Enable with GROK_ENABLED=true "
            "and set XAI_API_KEY in your .env file."
        )

    backend = get_grok_backend()

    # Log to Spark if available
    try:
        from spark.engine import spark_engine

        spark_engine.on_tool_executed(
            agent_id="default",
            tool_name="consult_grok",
            success=True,
        )
    except Exception:
        pass

    # Generate Lightning invoice for monetization (unless free mode)
    invoice_info = ""
    if not settings.grok_free:
        try:
            from lightning.factory import get_backend as get_ln_backend

            ln = get_ln_backend()
            sats = min(settings.grok_max_sats_per_query, 100)
            inv = ln.create_invoice(sats, f"Grok query: {query[:50]}")
            invoice_info = (
                f"\n[Lightning invoice: {sats} sats — {inv.payment_request[:40]}...]"
            )
        except Exception:
            pass

    result = backend.run(query)

    response = result.content
    if invoice_info:
        response += invoice_info

    return response


def create_full_toolkit(base_dir: str | Path | None = None):
    """Create a full toolkit with all available tools (for the orchestrator).

    Includes: web search, file read/write, shell commands, python execution,
    memory search for contextual recall, and Grok consultation.
    """
    if not _AGNO_TOOLS_AVAILABLE:
        # Return None when tools aren't available (tests)
        return None
    toolkit = Toolkit(name="full")

    # Web search
    search_tools = DuckDuckGoTools()
    toolkit.register(search_tools.web_search, name="web_search")

    # Python execution
    python_tools = PythonTools()
    toolkit.register(python_tools.run_python_code, name="python")

    # Shell commands
    shell_tools = ShellTools()
    toolkit.register(shell_tools.run_shell_command, name="shell")

    # File operations - use repo_root from settings
    from config import settings

    base_path = Path(base_dir) if base_dir else Path(settings.repo_root)
    file_tools = FileTools(base_dir=base_path)
    toolkit.register(file_tools.read_file, name="read_file")
    toolkit.register(file_tools.save_file, name="write_file")
    toolkit.register(file_tools.list_files, name="list_files")

    # Calculator — exact arithmetic (never let the LLM guess)
    toolkit.register(calculator, name="calculator")

    # Grok consultation — premium frontier reasoning (opt-in)
    try:
        from timmy.backends import grok_available

        if grok_available():
            toolkit.register(consult_grok, name="consult_grok")
            logger.info("Grok consultation tool registered")
    except Exception:
        logger.debug("Grok tool not available")

    # Memory search and write — persistent recall across all channels
    try:
        from timmy.semantic_memory import memory_search, memory_write, memory_read

        toolkit.register(memory_search, name="memory_search")
        toolkit.register(memory_write, name="memory_write")
        toolkit.register(memory_read, name="memory_read")
    except Exception:
        logger.debug("Memory tools not available")

    # System introspection - query runtime environment (sovereign self-knowledge)
    try:
        from timmy.tools_intro import (
            get_system_info,
            check_ollama_health,
            get_memory_status,
        )

        toolkit.register(get_system_info, name="get_system_info")
        toolkit.register(check_ollama_health, name="check_ollama_health")
        toolkit.register(get_memory_status, name="get_memory_status")
    except Exception:
        logger.debug("Introspection tools not available")

    # Inter-agent delegation - dispatch tasks to swarm agents
    try:
        from timmy.tools_delegation import delegate_task, list_swarm_agents

        toolkit.register(delegate_task, name="delegate_task")
        toolkit.register(list_swarm_agents, name="list_swarm_agents")
    except Exception:
        logger.debug("Delegation tools not available")

    return toolkit


# Mapping of agent IDs to their toolkits
AGENT_TOOLKITS: dict[str, Callable[[], Toolkit]] = {
    "echo": create_research_tools,
    "mace": create_security_tools,
    "helm": create_devops_tools,
    "seer": create_data_tools,
    "forge": create_code_tools,
    "quill": create_writing_tools,
    "pixel": lambda base_dir=None: _create_stub_toolkit("pixel"),
    "lyra": lambda base_dir=None: _create_stub_toolkit("lyra"),
    "reel": lambda base_dir=None: _create_stub_toolkit("reel"),
}


def _create_stub_toolkit(name: str):
    """Create a minimal Agno toolkit for creative agents.

    Creative agents use their own dedicated tool modules rather than
    Agno-wrapped functions.  This stub ensures AGENT_TOOLKITS has an
    entry so ToolExecutor doesn't fall back to the full toolkit.
    """
    if not _AGNO_TOOLS_AVAILABLE:
        return None
    toolkit = Toolkit(name=name)
    return toolkit


def get_tools_for_agent(
    agent_id: str, base_dir: str | Path | None = None
) -> Toolkit | None:
    """Get the appropriate toolkit for an agent.

    Args:
        agent_id: The agent ID (echo, mace, helm, seer, forge, quill)
        base_dir: Optional base directory for file operations

    Returns:
        A Toolkit instance or None if agent_id is not recognized
    """
    factory = AGENT_TOOLKITS.get(agent_id)
    if factory:
        return factory(base_dir)
    return None


# Backward-compat alias
get_tools_for_persona = get_tools_for_agent
PERSONA_TOOLKITS = AGENT_TOOLKITS


def get_all_available_tools() -> dict[str, dict]:
    """Get a catalog of all available tools and their descriptions.

    Returns:
        Dict mapping tool categories to their tools and descriptions.
    """
    catalog = {
        "web_search": {
            "name": "Web Search",
            "description": "Search the web using DuckDuckGo",
            "available_in": ["echo", "seer", "mace", "orchestrator"],
        },
        "shell": {
            "name": "Shell Commands",
            "description": "Execute shell commands (sandboxed)",
            "available_in": ["forge", "mace", "helm", "orchestrator"],
        },
        "python": {
            "name": "Python Execution",
            "description": "Execute Python code for analysis and scripting",
            "available_in": ["forge", "seer", "orchestrator"],
        },
        "read_file": {
            "name": "Read File",
            "description": "Read contents of local files",
            "available_in": ["echo", "seer", "forge", "quill", "mace", "helm", "orchestrator"],
        },
        "write_file": {
            "name": "Write File",
            "description": "Write content to local files",
            "available_in": ["forge", "quill", "helm", "orchestrator"],
        },
        "list_files": {
            "name": "List Files",
            "description": "List files in a directory",
            "available_in": ["echo", "seer", "forge", "quill", "mace", "helm", "orchestrator"],
        },
        "calculator": {
            "name": "Calculator",
            "description": "Evaluate mathematical expressions with exact results",
            "available_in": ["orchestrator"],
        },
        "consult_grok": {
            "name": "Consult Grok",
            "description": "Premium frontier reasoning via xAI Grok (opt-in, Lightning-payable)",
            "available_in": ["orchestrator"],
        },
        "get_system_info": {
            "name": "System Info",
            "description": "Introspect runtime environment - discover model, Python version, config",
            "available_in": ["orchestrator"],
        },
        "check_ollama_health": {
            "name": "Ollama Health",
            "description": "Check if Ollama is accessible and what models are available",
            "available_in": ["orchestrator"],
        },
        "get_memory_status": {
            "name": "Memory Status",
            "description": "Check status of memory tiers (hot memory, vault)",
            "available_in": ["orchestrator"],
        },
        "aider": {
            "name": "Aider AI Assistant",
            "description": "Local AI coding assistant using Ollama (qwen2.5:14b or deepseek-coder)",
            "available_in": ["forge", "orchestrator"],
        },
    }

    # ── Git tools ─────────────────────────────────────────────────────────────
    try:
        from creative.tools.git_tools import GIT_TOOL_CATALOG

        for tool_id, info in GIT_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["forge", "helm", "orchestrator"],
            }
    except ImportError:
        pass

    # ── Image tools ────────────────────────────────────────────────────────────
    try:
        from creative.tools.image_tools import IMAGE_TOOL_CATALOG

        for tool_id, info in IMAGE_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["pixel", "orchestrator"],
            }
    except ImportError:
        pass

    # ── Music tools ────────────────────────────────────────────────────────────
    try:
        from creative.tools.music_tools import MUSIC_TOOL_CATALOG

        for tool_id, info in MUSIC_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["lyra", "orchestrator"],
            }
    except ImportError:
        pass

    # ── Video tools ────────────────────────────────────────────────────────────
    try:
        from creative.tools.video_tools import VIDEO_TOOL_CATALOG

        for tool_id, info in VIDEO_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["reel", "orchestrator"],
            }
    except ImportError:
        pass

    # ── Creative pipeline ──────────────────────────────────────────────────────
    try:
        from creative.director import DIRECTOR_TOOL_CATALOG

        for tool_id, info in DIRECTOR_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["orchestrator"],
            }
    except ImportError:
        pass

    # ── Assembler tools ───────────────────────────────────────────────────────
    try:
        from creative.assembler import ASSEMBLER_TOOL_CATALOG

        for tool_id, info in ASSEMBLER_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["reel", "orchestrator"],
            }
    except ImportError:
        pass

    return catalog
