"""Tool execution layer for swarm agents.

Bridges PersonaNodes with MCP tools, enabling agents to actually
do work when they win a task auction.

Usage:
    executor = ToolExecutor.for_persona("forge", agent_id="forge-001")
    result = executor.execute_task("Write a function to calculate fibonacci")
"""

import logging
from typing import Any, Optional
from pathlib import Path

from timmy.tools import get_tools_for_persona, create_full_toolkit
from timmy.agent import create_timmy

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tasks using persona-appropriate tools.
    
    Each persona gets a different set of tools based on their specialty:
    - Echo: web search, file reading
    - Forge: shell, python, file read/write, git
    - Seer: python, file reading
    - Quill: file read/write
    - Mace: shell, web search
    - Helm: shell, file operations, git
    - Pixel: image generation, storyboards
    - Lyra: music/song generation
    - Reel: video generation, assembly
    
    The executor combines:
    1. MCP tools (file, shell, python, search)
    2. LLM reasoning (via Ollama) to decide which tools to use
    3. Task execution and result formatting
    """
    
    def __init__(
        self,
        persona_id: str,
        agent_id: str,
        base_dir: Optional[Path] = None,
    ) -> None:
        """Initialize tool executor for a persona.
        
        Args:
            persona_id: The persona type (echo, forge, etc.)
            agent_id: Unique agent instance ID
            base_dir: Base directory for file operations
        """
        self._persona_id = persona_id
        self._agent_id = agent_id
        self._base_dir = base_dir or Path.cwd()
        
        # Get persona-specific tools
        try:
            self._toolkit = get_tools_for_persona(persona_id, base_dir)
            if self._toolkit is None:
                logger.warning(
                    "No toolkit available for persona %s, using full toolkit",
                    persona_id
                )
                self._toolkit = create_full_toolkit(base_dir)
        except ImportError as exc:
            logger.warning(
                "Tools not available for %s (Agno not installed): %s",
                persona_id, exc
            )
            self._toolkit = None
        
        # Create LLM agent for reasoning about tool use
        # The agent uses the toolkit to decide what actions to take
        try:
            self._llm = create_timmy()
        except Exception as exc:
            logger.warning("Failed to create LLM agent: %s", exc)
            self._llm = None
        
        logger.info(
            "ToolExecutor initialized for %s (%s) with %d tools",
            persona_id, agent_id, len(self._toolkit.functions) if self._toolkit else 0
        )
    
    @classmethod
    def for_persona(
        cls,
        persona_id: str,
        agent_id: str,
        base_dir: Optional[Path] = None,
    ) -> "ToolExecutor":
        """Factory method to create executor for a persona."""
        return cls(persona_id, agent_id, base_dir)
    
    def execute_task(self, task_description: str) -> dict[str, Any]:
        """Execute a task using appropriate tools.
        
        This is the main entry point. The executor:
        1. Analyzes the task
        2. Decides which tools to use
        3. Executes them (potentially multiple rounds)
        4. Formats the result
        
        Args:
            task_description: What needs to be done
            
        Returns:
            Dict with result, tools_used, and any errors
        """
        if self._toolkit is None:
            return {
                "success": False,
                "error": "No toolkit available",
                "result": None,
                "tools_used": [],
            }
        
        tools_used = []
        
        try:
            # For now, use a simple approach: let the LLM decide what to do
            # In the future, this could be more sophisticated with multi-step planning
            
            # Log what tools would be appropriate (in future, actually execute them)
            # For now, we track which tools were likely needed based on keywords
            likely_tools = self._infer_tools_needed(task_description)
            tools_used = likely_tools
            
            if self._llm is None:
                # No LLM available - return simulated response
                response_text = (
                    f"[Simulated {self._persona_id} response] "
                    f"Would execute task using tools: {', '.join(tools_used) or 'none'}"
                )
            else:
                # Build system prompt describing available tools
                tool_descriptions = self._describe_tools()
                
                prompt = f"""You are a {self._persona_id} specialist agent. 

Your task: {task_description}

Available tools:
{tool_descriptions}

Think step by step about what tools you need to use, then provide your response.
If you need to use tools, describe what you would do. If the task is conversational, just respond naturally.

Response:"""
                
                # Run the LLM with tool awareness
                result = self._llm.run(prompt, stream=False)
                response_text = result.content if hasattr(result, "content") else str(result)
            
            logger.info(
                "Task executed by %s: %d tools likely needed",
                self._agent_id, len(tools_used)
            )
            
            return {
                "success": True,
                "result": response_text,
                "tools_used": tools_used,
                "persona_id": self._persona_id,
                "agent_id": self._agent_id,
            }
            
        except Exception as exc:
            logger.exception("Task execution failed for %s", self._agent_id)
            return {
                "success": False,
                "error": str(exc),
                "result": None,
                "tools_used": tools_used,
            }
    
    def _describe_tools(self) -> str:
        """Create human-readable description of available tools."""
        if not self._toolkit:
            return "No tools available"
        
        descriptions = []
        for func in self._toolkit.functions:
            name = getattr(func, 'name', func.__name__)
            doc = func.__doc__ or "No description"
            # Take first line of docstring
            doc_first_line = doc.strip().split('\n')[0]
            descriptions.append(f"- {name}: {doc_first_line}")
        
        return '\n'.join(descriptions)
    
    def _infer_tools_needed(self, task_description: str) -> list[str]:
        """Infer which tools would be needed for a task.
        
        This is a simple keyword-based approach. In the future,
        this could use the LLM to explicitly choose tools.
        """
        task_lower = task_description.lower()
        tools = []
        
        # Map keywords to likely tools
        keyword_tool_map = {
            "search": "web_search",
            "find": "web_search",
            "look up": "web_search",
            "read": "read_file",
            "file": "read_file",
            "write": "write_file",
            "save": "write_file",
            "code": "python",
            "function": "python",
            "script": "python",
            "shell": "shell",
            "command": "shell",
            "run": "shell",
            "list": "list_files",
            "directory": "list_files",
            # Git operations
            "commit": "git_commit",
            "branch": "git_branch",
            "push": "git_push",
            "pull": "git_pull",
            "diff": "git_diff",
            "clone": "git_clone",
            "merge": "git_branch",
            "stash": "git_stash",
            "blame": "git_blame",
            "git status": "git_status",
            "git log": "git_log",
            # Image generation
            "image": "generate_image",
            "picture": "generate_image",
            "storyboard": "generate_storyboard",
            "illustration": "generate_image",
            # Music generation
            "music": "generate_song",
            "song": "generate_song",
            "vocal": "generate_vocals",
            "instrumental": "generate_instrumental",
            "lyrics": "generate_song",
            # Video generation
            "video": "generate_video_clip",
            "clip": "generate_video_clip",
            "animate": "image_to_video",
            "film": "generate_video_clip",
            # Assembly
            "stitch": "stitch_clips",
            "assemble": "run_assembly",
            "title card": "add_title_card",
            "subtitle": "add_subtitles",
        }
        
        for keyword, tool in keyword_tool_map.items():
            if keyword in task_lower and tool not in tools:
                # Add tool if available in this executor's toolkit
                # or if toolkit is None (for inference without execution)
                if self._toolkit is None or any(
                    getattr(f, 'name', f.__name__) == tool 
                    for f in self._toolkit.functions
                ):
                    tools.append(tool)
        
        return tools
    
    def get_capabilities(self) -> list[str]:
        """Return list of tool names this executor has access to."""
        if not self._toolkit:
            return []
        return [
            getattr(f, 'name', f.__name__) 
            for f in self._toolkit.functions
        ]


class DirectToolExecutor(ToolExecutor):
    """Tool executor that actually calls tools directly.

    For code-modification tasks assigned to the Forge persona, dispatches
    to the SelfModifyLoop for real edit → test → commit execution.
    Other tasks fall back to the simulated parent.
    """

    _CODE_KEYWORDS = frozenset({
        "modify", "edit", "fix", "refactor", "implement",
        "add function", "change code", "update source", "patch",
    })

    def execute_with_tools(self, task_description: str) -> dict[str, Any]:
        """Execute tools to complete the task.

        Code-modification tasks on the Forge persona are routed through
        the SelfModifyLoop.  Everything else delegates to the parent.
        """
        task_lower = task_description.lower()
        is_code_task = any(kw in task_lower for kw in self._CODE_KEYWORDS)

        if is_code_task and self._persona_id == "forge":
            try:
                from config import settings as cfg
                if not cfg.self_modify_enabled:
                    return self.execute_task(task_description)

                from self_modify.loop import SelfModifyLoop, ModifyRequest

                loop = SelfModifyLoop()
                result = loop.run(ModifyRequest(instruction=task_description))

                return {
                    "success": result.success,
                    "result": (
                        f"Modified {len(result.files_changed)} file(s). "
                        f"Tests {'passed' if result.test_passed else 'failed'}."
                    ),
                    "tools_used": ["read_file", "write_file", "shell", "git_commit"],
                    "persona_id": self._persona_id,
                    "agent_id": self._agent_id,
                    "commit_sha": result.commit_sha,
                }
            except Exception as exc:
                logger.exception("Direct tool execution failed")
                return {
                    "success": False,
                    "error": str(exc),
                    "result": None,
                    "tools_used": [],
                }

        return self.execute_task(task_description)
