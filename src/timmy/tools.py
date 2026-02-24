"""Timmy Tools — sovereign, local-first tool integration.

Provides Timmy and swarm agents with capabilities for:
- Web search (DuckDuckGo)
- File read/write (local filesystem)
- Shell command execution (sandboxed)
- Python code execution
- Git operations (clone, commit, push, pull, branch, diff, etc.)
- Image generation (FLUX text-to-image, storyboards)
- Music generation (ACE-Step vocals + instrumentals)
- Video generation (Wan 2.1 text-to-video, image-to-video)
- Creative pipeline (storyboard → music → video → assembly)

Tools are assigned to personas based on their specialties:
- Echo (Research): web search, file read
- Forge (Code): shell, python execution, file write, git
- Seer (Data): python execution, file read
- Quill (Writing): file read/write
- Helm (DevOps): shell, file operations, git
- Mace (Security): shell, web search, file read
- Pixel (Visual): image generation, storyboards
- Lyra (Music): song/vocal/instrumental generation
- Reel (Video): video clip generation, image-to-video
"""

from __future__ import annotations

import logging
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
class PersonaTools:
    """Tools assigned to a persona/agent."""
    agent_id: str
    agent_name: str
    toolkit: Toolkit
    available_tools: list[str] = field(default_factory=list)


def _track_tool_usage(agent_id: str, tool_name: str, success: bool = True) -> None:
    """Track tool usage for analytics."""
    if agent_id not in _TOOL_USAGE:
        _TOOL_USAGE[agent_id] = []
    _TOOL_USAGE[agent_id].append({
        "tool": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": success,
    })


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


def create_research_tools(base_dir: str | Path | None = None):
    """Create tools for research personas (Echo).
    
    Includes: web search, file reading
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="research")
    
    # Web search via DuckDuckGo
    search_tools = DuckDuckGoTools()
    toolkit.add_tool(search_tools.web_search, name="web_search")
    
    # File reading
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


def create_code_tools(base_dir: str | Path | None = None):
    """Create tools for coding personas (Forge).
    
    Includes: shell commands, python execution, file read/write
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="code")
    
    # Shell commands (sandboxed)
    shell_tools = ShellTools()
    toolkit.add_tool(shell_tools.run_shell_command, name="shell")
    
    # Python execution
    python_tools = PythonTools()
    toolkit.add_tool(python_tools.python, name="python")
    
    # File operations
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.write_file, name="write_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


def create_data_tools(base_dir: str | Path | None = None):
    """Create tools for data personas (Seer).
    
    Includes: python execution, file reading, web search for data sources
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="data")
    
    # Python execution for analysis
    python_tools = PythonTools()
    toolkit.add_tool(python_tools.python, name="python")
    
    # File reading
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    # Web search for finding datasets
    search_tools = DuckDuckGoTools()
    toolkit.add_tool(search_tools.web_search, name="web_search")
    
    return toolkit


def create_writing_tools(base_dir: str | Path | None = None):
    """Create tools for writing personas (Quill).
    
    Includes: file read/write
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="writing")
    
    # File operations
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.write_file, name="write_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


def create_security_tools(base_dir: str | Path | None = None):
    """Create tools for security personas (Mace).
    
    Includes: shell commands (for scanning), web search (for threat intel), file read
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="security")
    
    # Shell for running security scans
    shell_tools = ShellTools()
    toolkit.add_tool(shell_tools.run_shell_command, name="shell")
    
    # Web search for threat intelligence
    search_tools = DuckDuckGoTools()
    toolkit.add_tool(search_tools.web_search, name="web_search")
    
    # File reading for logs/configs
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


def create_devops_tools(base_dir: str | Path | None = None):
    """Create tools for DevOps personas (Helm).
    
    Includes: shell commands, file read/write
    """
    if not _AGNO_TOOLS_AVAILABLE:
        raise ImportError(f"Agno tools not available: {_ImportError}")
    toolkit = Toolkit(name="devops")
    
    # Shell for deployment commands
    shell_tools = ShellTools()
    toolkit.add_tool(shell_tools.run_shell_command, name="shell")
    
    # File operations for config management
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.write_file, name="write_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


def create_full_toolkit(base_dir: str | Path | None = None):
    """Create a full toolkit with all available tools (for Timmy).
    
    Includes: web search, file read/write, shell commands, python execution
    """
    if not _AGNO_TOOLS_AVAILABLE:
        # Return None when tools aren't available (tests)
        return None
    toolkit = Toolkit(name="full")
    
    # Web search
    search_tools = DuckDuckGoTools()
    toolkit.add_tool(search_tools.web_search, name="web_search")
    
    # Python execution
    python_tools = PythonTools()
    toolkit.add_tool(python_tools.python, name="python")
    
    # Shell commands
    shell_tools = ShellTools()
    toolkit.add_tool(shell_tools.run_shell_command, name="shell")
    
    # File operations
    base_path = Path(base_dir) if base_dir else Path.cwd()
    file_tools = FileTools(base_dir=str(base_path))
    toolkit.add_tool(file_tools.read_file, name="read_file")
    toolkit.add_tool(file_tools.write_file, name="write_file")
    toolkit.add_tool(file_tools.list_files, name="list_files")
    
    return toolkit


# Mapping of persona IDs to their toolkits
PERSONA_TOOLKITS: dict[str, Callable[[], Toolkit]] = {
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
    """Create a minimal Agno toolkit for creative personas.

    Creative personas use their own dedicated tool modules (tools.image_tools,
    tools.music_tools, tools.video_tools) rather than Agno-wrapped functions.
    This stub ensures PERSONA_TOOLKITS has an entry so ToolExecutor doesn't
    fall back to the full toolkit.
    """
    if not _AGNO_TOOLS_AVAILABLE:
        return None
    toolkit = Toolkit(name=name)
    return toolkit


def get_tools_for_persona(persona_id: str, base_dir: str | Path | None = None) -> Toolkit | None:
    """Get the appropriate toolkit for a persona.
    
    Args:
        persona_id: The persona ID (echo, mace, helm, seer, forge, quill)
        base_dir: Optional base directory for file operations
    
    Returns:
        A Toolkit instance or None if persona_id is not recognized
    """
    factory = PERSONA_TOOLKITS.get(persona_id)
    if factory:
        return factory(base_dir)
    return None


def get_all_available_tools() -> dict[str, dict]:
    """Get a catalog of all available tools and their descriptions.

    Returns:
        Dict mapping tool categories to their tools and descriptions.
    """
    catalog = {
        "web_search": {
            "name": "Web Search",
            "description": "Search the web using DuckDuckGo",
            "available_in": ["echo", "seer", "mace", "timmy"],
        },
        "shell": {
            "name": "Shell Commands",
            "description": "Execute shell commands (sandboxed)",
            "available_in": ["forge", "mace", "helm", "timmy"],
        },
        "python": {
            "name": "Python Execution",
            "description": "Execute Python code for analysis and scripting",
            "available_in": ["forge", "seer", "timmy"],
        },
        "read_file": {
            "name": "Read File",
            "description": "Read contents of local files",
            "available_in": ["echo", "seer", "forge", "quill", "mace", "helm", "timmy"],
        },
        "write_file": {
            "name": "Write File",
            "description": "Write content to local files",
            "available_in": ["forge", "quill", "helm", "timmy"],
        },
        "list_files": {
            "name": "List Files",
            "description": "List files in a directory",
            "available_in": ["echo", "seer", "forge", "quill", "mace", "helm", "timmy"],
        },
    }

    # ── Git tools ─────────────────────────────────────────────────────────────
    try:
        from tools.git_tools import GIT_TOOL_CATALOG
        for tool_id, info in GIT_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["forge", "helm", "timmy"],
            }
    except ImportError:
        pass

    # ── Image tools (Pixel) ───────────────────────────────────────────────────
    try:
        from tools.image_tools import IMAGE_TOOL_CATALOG
        for tool_id, info in IMAGE_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["pixel", "timmy"],
            }
    except ImportError:
        pass

    # ── Music tools (Lyra) ────────────────────────────────────────────────────
    try:
        from tools.music_tools import MUSIC_TOOL_CATALOG
        for tool_id, info in MUSIC_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["lyra", "timmy"],
            }
    except ImportError:
        pass

    # ── Video tools (Reel) ────────────────────────────────────────────────────
    try:
        from tools.video_tools import VIDEO_TOOL_CATALOG
        for tool_id, info in VIDEO_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["reel", "timmy"],
            }
    except ImportError:
        pass

    # ── Creative pipeline (Director) ──────────────────────────────────────────
    try:
        from creative.director import DIRECTOR_TOOL_CATALOG
        for tool_id, info in DIRECTOR_TOOL_CATALOG.items():
            catalog[tool_id] = {
                "name": info["name"],
                "description": info["description"],
                "available_in": ["timmy"],
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
                "available_in": ["reel", "timmy"],
            }
    except ImportError:
        pass

    return catalog
