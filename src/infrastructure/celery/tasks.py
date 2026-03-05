"""Celery task definitions for background processing.

Tasks:
- run_agent_chat: Execute a chat prompt via Timmy's session
- execute_tool: Run a specific tool function asynchronously
- run_thinking_cycle: Execute one thinking engine cycle
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_app():
    """Get the Celery app (lazy import to avoid circular deps)."""
    from infrastructure.celery.app import celery_app
    return celery_app


_app = _get_app()

if _app is not None:

    @_app.task(bind=True, name="infrastructure.celery.tasks.run_agent_chat")
    def run_agent_chat(self, prompt, agent_id="timmy", session_id="celery"):
        """Execute a chat prompt against Timmy's agent session.

        Args:
            prompt: The message to send to the agent.
            agent_id: Agent identifier (currently only "timmy" supported).
            session_id: Chat session ID for context continuity.

        Returns:
            Dict with agent_id, response, and completed_at.
        """
        logger.info("Celery task [%s]: chat prompt for %s", self.request.id, agent_id)
        try:
            from timmy.session import chat
            response = chat(prompt, session_id=session_id)
            result = {
                "agent_id": agent_id,
                "prompt": prompt[:200],
                "response": response,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            _log_completion("run_agent_chat", self.request.id, success=True)
            return result
        except Exception as exc:
            logger.error("Celery chat task failed: %s", exc)
            _log_completion("run_agent_chat", self.request.id, success=False)
            return {
                "agent_id": agent_id,
                "prompt": prompt[:200],
                "error": str(exc),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

    @_app.task(bind=True, name="infrastructure.celery.tasks.execute_tool")
    def execute_tool(self, tool_name, kwargs=None, agent_id="timmy"):
        """Run a specific tool function asynchronously.

        Args:
            tool_name: Name of the tool to execute (e.g., "web_search").
            kwargs: Dict of keyword arguments for the tool.
            agent_id: Agent requesting the tool execution.

        Returns:
            Dict with tool_name, result, and success flag.
        """
        kwargs = kwargs or {}
        logger.info("Celery task [%s]: tool=%s for %s", self.request.id, tool_name, agent_id)
        try:
            from timmy.tools import create_full_toolkit
            toolkit = create_full_toolkit()
            if toolkit is None:
                return {"tool_name": tool_name, "error": "Toolkit unavailable", "success": False}

            # Find and call the tool function
            tool_fn = None
            for fn in toolkit.functions.values():
                if fn.name == tool_name:
                    tool_fn = fn
                    break

            if tool_fn is None:
                return {"tool_name": tool_name, "error": f"Tool '{tool_name}' not found", "success": False}

            result = tool_fn.entrypoint(**kwargs)
            _log_completion("execute_tool", self.request.id, success=True)
            return {
                "tool_name": tool_name,
                "result": str(result)[:5000],
                "success": True,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("Celery tool task failed: %s", exc)
            _log_completion("execute_tool", self.request.id, success=False)
            return {"tool_name": tool_name, "error": str(exc), "success": False}

    @_app.task(bind=True, name="infrastructure.celery.tasks.run_thinking_cycle")
    def run_thinking_cycle(self):
        """Execute one thinking engine cycle in the background.

        Returns:
            Dict with thought data or None if thinking is disabled.
        """
        import asyncio

        logger.info("Celery task [%s]: thinking cycle", self.request.id)
        try:
            from timmy.thinking import thinking_engine

            # Run the async think_once in a sync context
            loop = asyncio.new_event_loop()
            try:
                thought = loop.run_until_complete(thinking_engine.think_once())
            finally:
                loop.close()

            if thought:
                _log_completion("run_thinking_cycle", self.request.id, success=True)
                return {
                    "thought_id": thought.id,
                    "content": thought.content,
                    "seed_type": thought.seed_type,
                    "created_at": thought.created_at,
                }
            return None
        except Exception as exc:
            logger.error("Celery thinking task failed: %s", exc)
            _log_completion("run_thinking_cycle", self.request.id, success=False)
            return None


def _log_completion(task_name, task_id, success=True):
    """Log task completion to the Spark engine if available."""
    try:
        from spark.engine import spark_engine
        spark_engine.on_tool_executed(
            agent_id="celery-worker",
            tool_name=f"celery.{task_name}",
            success=success,
        )
    except Exception:
        pass
