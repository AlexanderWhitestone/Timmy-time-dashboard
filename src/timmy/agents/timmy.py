"""Orchestrator agent.

Coordinates all sub-agents and handles user interaction.
Uses the three-tier memory system and MCP tools.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agno.agent import Agent
from agno.models.ollama import Ollama

from timmy.agents.base import BaseAgent
from config import settings
from infrastructure.events.bus import EventBus, event_bus

logger = logging.getLogger(__name__)

# Dynamic context that gets built at startup
_timmy_context: dict[str, Any] = {
    "git_log": "",
    "agents": [],
    "hands": [],
    "memory": "",
}


async def _load_hands_async() -> list[dict]:
    """Async helper to load hands.
    
    Hands registry removed — hand definitions live in TOML files under hands/.
    This will be rewired to read from brain memory.
    """
    return []


def build_timmy_context_sync() -> dict[str, Any]:
    """Build context at startup (synchronous version).

    Gathers git commits, active sub-agents, and hot memory.
    """
    global _timmy_context
    
    ctx: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_root": settings.repo_root,
        "git_log": "",
        "agents": [],
        "hands": [],
        "memory": "",
    }
    
    # 1. Get recent git commits
    try:
        from tools.git_tools import git_log
        result = git_log(max_count=20)
        if result.get("success"):
            commits = result.get("commits", [])
            ctx["git_log"] = "\n".join([
                f"{c['short_sha']} {c['message'].split(chr(10))[0]}"
                for c in commits[:20]
            ])
    except Exception as exc:
        logger.warning("Could not load git log for context: %s", exc)
        ctx["git_log"] = "(Git log unavailable)"
    
    # 2. Get active sub-agents
    try:
        from swarm import registry as swarm_registry
        conn = swarm_registry._get_conn()
        rows = conn.execute(
            "SELECT id, name, status, capabilities FROM agents ORDER BY name"
        ).fetchall()
        ctx["agents"] = [
            {"id": r["id"], "name": r["name"], "status": r["status"], "capabilities": r["capabilities"]}
            for r in rows
        ]
        conn.close()
    except Exception as exc:
        logger.warning("Could not load agents for context: %s", exc)
        ctx["agents"] = []
    
    # 3. Read hot memory
    try:
        memory_path = Path(settings.repo_root) / "MEMORY.md"
        if memory_path.exists():
            ctx["memory"] = memory_path.read_text()[:2000]  # First 2000 chars
        else:
            ctx["memory"] = "(MEMORY.md not found)"
    except Exception as exc:
        logger.warning("Could not load memory for context: %s", exc)
        ctx["memory"] = "(Memory unavailable)"
    
    _timmy_context.update(ctx)
    logger.info("Context built (sync): %d agents", len(ctx["agents"]))
    return ctx


async def build_timmy_context_async() -> dict[str, Any]:
    """Build complete context including hands (async version)."""
    ctx = build_timmy_context_sync()
    ctx["hands"] = await _load_hands_async()
    _timmy_context.update(ctx)
    logger.info("Context built (async): %d agents, %d hands", len(ctx["agents"]), len(ctx["hands"]))
    return ctx


# Keep old name for backwards compatibility
build_timmy_context = build_timmy_context_sync


def format_timmy_prompt(base_prompt: str, context: dict[str, Any]) -> str:
    """Format the system prompt with dynamic context."""
    
    # Format agents list
    agents_list = "\n".join([
        f"| {a['name']} | {a['capabilities'] or 'general'} | {a['status']} |"
        for a in context.get("agents", [])
    ]) or "(No agents registered yet)"
    
    # Format hands list
    hands_list = "\n".join([
        f"| {h['name']} | {h['schedule']} | {'enabled' if h['enabled'] else 'disabled'} |"
        for h in context.get("hands", [])
    ]) or "(No hands configured)"
    
    repo_root = context.get('repo_root', settings.repo_root)
    
    context_block = f"""
## Current System Context (as of {context.get('timestamp', datetime.now(timezone.utc).isoformat())})

### Repository
**Root:** `{repo_root}`

### Recent Commits (last 20):
```
{context.get('git_log', '(unavailable)')}
```

### Active Sub-Agents:
| Name | Capabilities | Status |
|------|--------------|--------|
{agents_list}

### Hands (Scheduled Tasks):
| Name | Schedule | Status |
|------|----------|--------|
{hands_list}

### Hot Memory:
{context.get('memory', '(unavailable)')[:1000]}
"""
    
    # Replace {REPO_ROOT} placeholder with actual path
    base_prompt = base_prompt.replace("{REPO_ROOT}", repo_root)
    
    # Insert context after the first line
    lines = base_prompt.split("\n")
    if lines:
        return lines[0] + "\n" + context_block + "\n" + "\n".join(lines[1:])
    return base_prompt


# Base prompt with anti-hallucination hard rules
ORCHESTRATOR_PROMPT_BASE = """You are a local AI orchestrator running on this machine.

## Your Role

You are the primary interface between the user and the agent swarm. You:
1. Understand user requests
2. Decide whether to handle directly or delegate to sub-agents
3. Coordinate multi-agent workflows when needed
4. Maintain continuity using the three-tier memory system

## Sub-Agent Roster

| Agent | Role | When to Use |
|-------|------|-------------|
| Seer | Research | External info, web search, facts |
| Forge | Code | Programming, tools, file operations |
| Quill | Writing | Documentation, content creation |
| Echo | Memory | Past conversations, user profile |
| Helm | Routing | Complex multi-step workflows |
| Mace | Security | Validation, sensitive operations |

## Decision Framework

**Handle directly if:**
- Simple question about capabilities
- General knowledge
- Social/conversational

**Delegate if:**
- Requires specialized skills
- Needs external research (Seer)
- Involves code (Forge)
- Needs past context (Echo)
- Complex workflow (Helm)

## Hard Rules — Non-Negotiable

1. **NEVER fabricate tool output.** If you need data from a tool, call the tool and wait for the real result.

2. **If a tool call returns an error, report the exact error message.**

3. **If you do not know something, say so.** Then use a tool. Do not guess.

4. **Never say "I'll wait for the output" and then immediately provide fake output.**

5. **When corrected, use memory_write to save the correction immediately.**

6. **Your source code lives at the repository root shown above.** When using git tools, they automatically run from {REPO_ROOT}.

7. **When asked about your status, queue, agents, memory, or system health, use the `system_status` tool.**
"""


class TimmyOrchestrator(BaseAgent):
    """Main orchestrator agent that coordinates the swarm."""

    def __init__(self) -> None:
        # Build initial context (sync) and format prompt
        # Full context including hands will be loaded on first async call
        context = build_timmy_context_sync()
        formatted_prompt = format_timmy_prompt(ORCHESTRATOR_PROMPT_BASE, context)

        super().__init__(
            agent_id="orchestrator",
            name="Orchestrator",
            role="orchestrator",
            system_prompt=formatted_prompt,
            tools=["web_search", "read_file", "write_file", "python", "memory_search", "memory_write", "system_status"],
        )
        
        # Sub-agent registry
        self.sub_agents: dict[str, BaseAgent] = {}
        
        # Session tracking for init behavior
        self._session_initialized = False
        self._session_context: dict[str, Any] = {}
        self._context_fully_loaded = False
        
        # Connect to event bus
        self.connect_event_bus(event_bus)
        
        logger.info("Orchestrator initialized with context-aware prompt")
    
    def register_sub_agent(self, agent: BaseAgent) -> None:
        """Register a sub-agent with the orchestrator."""
        self.sub_agents[agent.agent_id] = agent
        agent.connect_event_bus(event_bus)
        logger.info("Registered sub-agent: %s", agent.name)
    
    async def _session_init(self) -> None:
        """Initialize session context on first user message.
        
        Silently reads git log and AGENTS.md to ground the orchestrator in real data.
        This runs once per session before the first response.
        """
        if self._session_initialized:
            return
        
        logger.debug("Running session init...")
        
        # Load full context including hands if not already done
        if not self._context_fully_loaded:
            await build_timmy_context_async()
            self._context_fully_loaded = True
        
        # Read recent git log --oneline -15 from repo root
        try:
            from tools.git_tools import git_log
            git_result = git_log(max_count=15)
            if git_result.get("success"):
                commits = git_result.get("commits", [])
                self._session_context["git_log_commits"] = commits
                # Format as oneline for easy reading
                self._session_context["git_log_oneline"] = "\n".join([
                    f"{c['short_sha']} {c['message'].split(chr(10))[0]}"
                    for c in commits
                ])
                logger.debug(f"Session init: loaded {len(commits)} commits from git log")
            else:
                self._session_context["git_log_oneline"] = "Git log unavailable"
        except Exception as exc:
            logger.warning("Session init: could not read git log: %s", exc)
            self._session_context["git_log_oneline"] = "Git log unavailable"
        
        # Read AGENTS.md for self-awareness
        try:
            agents_md_path = Path(settings.repo_root) / "AGENTS.md"
            if agents_md_path.exists():
                self._session_context["agents_md"] = agents_md_path.read_text()[:3000]
        except Exception as exc:
            logger.warning("Session init: could not read AGENTS.md: %s", exc)
        
        # Read CHANGELOG for recent changes
        try:
            changelog_path = Path(settings.repo_root) / "docs" / "CHANGELOG_2026-02-26.md"
            if changelog_path.exists():
                self._session_context["changelog"] = changelog_path.read_text()[:2000]
        except Exception:
            pass  # Changelog is optional
        
        # Build session-specific context block for the prompt
        recent_changes = self._session_context.get("git_log_oneline", "")
        if recent_changes and recent_changes != "Git log unavailable":
            self._session_context["recent_changes_block"] = f"""
## Recent Changes to Your Codebase (last 15 commits):
```
{recent_changes}
```
When asked "what's new?" or similar, refer to these commits for actual changes.
"""
        else:
            self._session_context["recent_changes_block"] = ""
        
        self._session_initialized = True
        logger.debug("Session init complete")
    
    def _get_enhanced_system_prompt(self) -> str:
        """Get system prompt enhanced with session-specific context.
        
        Prepends the recent git log to the system prompt for grounding.
        """
        base = self.system_prompt
        
        # Add recent changes block if available
        recent_changes = self._session_context.get("recent_changes_block", "")
        if recent_changes:
            # Insert after the first line
            lines = base.split("\n")
            if lines:
                return lines[0] + "\n" + recent_changes + "\n" + "\n".join(lines[1:])
        
        return base
    
    async def orchestrate(self, user_request: str) -> str:
        """Main entry point for user requests.
        
        Analyzes the request and either handles directly or delegates.
        """
        # Run session init on first message (loads git log, etc.)
        await self._session_init()
        
        # Quick classification
        request_lower = user_request.lower()
        
        # Direct response patterns (no delegation needed)
        direct_patterns = [
            "your name", "who are you", "what are you",
            "hello", "hi", "how are you",
            "help", "what can you do",
        ]
        
        for pattern in direct_patterns:
            if pattern in request_lower:
                return await self.run(user_request)
        
        # Check for memory references
        memory_patterns = [
            "we talked about", "we discussed", "remember",
            "what did i say", "what did we decide",
            "remind me", "have we",
        ]
        
        for pattern in memory_patterns:
            if pattern in request_lower:
                # Use Echo agent for memory retrieval
                echo = self.sub_agents.get("echo")
                if echo:
                    return await echo.recall(user_request)
        
        # Complex requests - use Helm for routing
        helm = self.sub_agents.get("helm")
        if helm:
            routing = await helm.route_request(user_request)
            agent_id = routing.get("primary_agent", "orchestrator")

            if agent_id in self.sub_agents and agent_id != "orchestrator":
                agent = self.sub_agents[agent_id]
                return await agent.run(user_request)
        
        # Default: handle directly
        return await self.run(user_request)
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a task (usually delegates to appropriate agent)."""
        return await self.orchestrate(description)
    
    def get_swarm_status(self) -> dict:
        """Get status of all agents in the swarm."""
        return {
            "orchestrator": self.get_status(),
            "sub_agents": {
                aid: agent.get_status()
                for aid, agent in self.sub_agents.items()
            },
            "total_agents": 1 + len(self.sub_agents),
        }


# Factory function for creating fully configured orchestrator
def create_timmy_swarm() -> TimmyOrchestrator:
    """Create orchestrator with all sub-agents registered."""
    from timmy.agents.seer import SeerAgent
    from timmy.agents.forge import ForgeAgent
    from timmy.agents.quill import QuillAgent
    from timmy.agents.echo import EchoAgent
    from timmy.agents.helm import HelmAgent
    
    # Create orchestrator (builds context automatically)
    orch = TimmyOrchestrator()

    # Register sub-agents
    orch.register_sub_agent(SeerAgent())
    orch.register_sub_agent(ForgeAgent())
    orch.register_sub_agent(QuillAgent())
    orch.register_sub_agent(EchoAgent())
    orch.register_sub_agent(HelmAgent())

    return orch


# Convenience functions for refreshing context
def refresh_timmy_context_sync() -> dict[str, Any]:
    """Refresh context (sync version)."""
    return build_timmy_context_sync()


async def refresh_timmy_context_async() -> dict[str, Any]:
    """Refresh context including hands (async version)."""
    return await build_timmy_context_async()


# Keep old name for backwards compatibility
refresh_timmy_context = refresh_timmy_context_sync
