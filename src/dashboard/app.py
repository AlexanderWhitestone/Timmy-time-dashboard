"""Optimized dashboard app with improved async handling and non-blocking startup.

Key improvements:
1. Background tasks use asyncio.create_task() to avoid blocking startup
2. Persona spawning is moved to a background task
3. MCP bootstrap is non-blocking
4. Chat integrations start in background
5. All startup operations complete quickly
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from dashboard.routes.agents import router as agents_router
from dashboard.routes.health import router as health_router
from dashboard.routes.swarm import router as swarm_router
from dashboard.routes.swarm import internal_router as swarm_internal_router
from dashboard.routes.marketplace import router as marketplace_router
from dashboard.routes.voice import router as voice_router
from dashboard.routes.mobile import router as mobile_router
from dashboard.routes.briefing import router as briefing_router
from dashboard.routes.telegram import router as telegram_router
from dashboard.routes.tools import router as tools_router
from dashboard.routes.spark import router as spark_router
from dashboard.routes.creative import router as creative_router
from dashboard.routes.discord import router as discord_router
from dashboard.routes.events import router as events_router
from dashboard.routes.ledger import router as ledger_router
from dashboard.routes.memory import router as memory_router
from dashboard.routes.router import router as router_status_router
from dashboard.routes.upgrades import router as upgrades_router
from dashboard.routes.work_orders import router as work_orders_router
from dashboard.routes.tasks import router as tasks_router
from dashboard.routes.scripture import router as scripture_router
from dashboard.routes.self_coding import router as self_coding_router
from dashboard.routes.self_coding import self_modify_router
from dashboard.routes.hands import router as hands_router
from dashboard.routes.grok import router as grok_router
from dashboard.routes.models import router as models_router
from dashboard.routes.models import api_router as models_api_router
from dashboard.routes.chat_api import router as chat_api_router
from dashboard.routes.thinking import router as thinking_router
from dashboard.routes.bugs import router as bugs_router
from infrastructure.router.api import router as cascade_router


def _configure_logging() -> None:
    """Configure logging with console and optional rotating file handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.addHandler(console)

    if settings.error_log_enabled:
        from logging.handlers import RotatingFileHandler

        log_dir = Path(settings.repo_root) / settings.error_log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        error_file = log_dir / "errors.log"

        file_handler = RotatingFileHandler(
            error_file,
            maxBytes=settings.error_log_max_bytes,
            backupCount=settings.error_log_backup_count,
        )
        file_handler.setLevel(logging.ERROR)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s — %(message)s\n"
                "  File: %(pathname)s:%(lineno)d\n"
                "  Function: %(funcName)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(file_handler)


_configure_logging()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent.parent

_BRIEFING_INTERVAL_HOURS = 6


async def _briefing_scheduler() -> None:
    """Background task: regenerate Timmy's briefing every 6 hours."""
    from timmy.briefing import engine as briefing_engine
    from infrastructure.notifications.push import notify_briefing_ready

    await asyncio.sleep(2)

    while True:
        try:
            if briefing_engine.needs_refresh():
                logger.info("Generating morning briefing…")
                briefing = briefing_engine.generate()
                await notify_briefing_ready(briefing)
            else:
                logger.info("Briefing is fresh; skipping generation.")
        except Exception as exc:
            logger.error("Briefing scheduler error: %s", exc)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(exc, source="briefing_scheduler")
            except Exception:
                pass

        await asyncio.sleep(_BRIEFING_INTERVAL_HOURS * 3600)


async def _thinking_loop() -> None:
    """Background task: Timmy's default thinking thread."""
    from swarm.task_queue.models import create_task
    from datetime import datetime

    await asyncio.sleep(10)

    while True:
        try:
            now = datetime.now()
            create_task(
                title=f"Thought: {now.strftime('%A %B %d, %I:%M %p')}",
                description="Continue thinking about your existence, recent events, scripture, creative ideas, or a previous thread of thought.",
                assigned_to="timmy",
                created_by="timmy",
                priority="low",
                requires_approval=False,
                auto_approve=True,
                task_type="thought",
            )
            logger.debug("Created thought task in queue")
        except Exception as exc:
            logger.error("Thinking loop error: %s", exc)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(exc, source="thinking_loop")
            except Exception:
                pass

        await asyncio.sleep(settings.thinking_interval_seconds)


def handle_bug_report(task):
    """Process a bug report: log the decision and dispatch a fix task to Forge.

    Timmy receives the bug report, decides it needs fixing, and creates
    a code_fix task assigned to Forge.  Every decision is logged to the
    event log so there is a full audit trail of what Timmy decided and why.
    """
    from swarm.event_log import EventType, log_event
    from swarm.task_queue.models import create_task

    decision = {
        "action": "dispatch_to_forge",
        "reason": f"Bug report received, dispatching fix to Forge: {task.title}",
        "priority": task.priority.value,
        "source_task_id": task.id,
    }

    # Dispatch a fix task to Forge
    try:
        fix_task = create_task(
            title=f"[Fix] {task.title}",
            description=(
                f"## Bug Report\n\n{task.description or task.title}\n\n"
                f"## Task\n\nImplement a fix for this bug and write a test proving the fix."
            ),
            assigned_to="forge",
            created_by="timmy",
            priority=task.priority.value,
            task_type="code_fix",
            requires_approval=False,
            auto_approve=True,
            parent_task_id=task.id,
        )
        decision["outcome"] = "fix_dispatched"
        decision["fix_task_id"] = fix_task.id
    except Exception as e:
        decision["outcome"] = "dispatch_failed"
        decision["error"] = str(e)

    # Log the decision trail to the event log
    try:
        log_event(
            EventType.BUG_REPORT_CREATED,
            source="bug_report_handler",
            task_id=task.id,
            agent_id="timmy",
            data=decision,
        )
    except Exception:
        pass

    # Return structured result (stored in task.result)
    if decision.get("fix_task_id"):
        return (
            f"Fix dispatched to Forge (task {decision['fix_task_id']}) | "
            f"Decision: {decision['reason']}"
        )
    return (
        f"Bug tracked internally (dispatch failed) | "
        f"Decision: {decision['reason']} | Error: {decision.get('error', 'unknown')}"
    )


async def _task_processor_loop() -> None:
    """Background task: Timmy's task queue processor."""
    from swarm.task_processor import task_processor
    from swarm.task_queue.models import update_task_status, list_tasks, TaskStatus
    from timmy.session import chat as timmy_chat
    from datetime import datetime
    import json

    await asyncio.sleep(5)

    def handle_chat_response(task):
        try:
            now = datetime.now()
            context = f"[System: Current date/time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}]\n\n"
            response = timmy_chat(context + task.description)

            # Log the real agent response to chat history
            try:
                from dashboard.store import message_log
                timestamp = now.strftime("%H:%M:%S")
                message_log.append(role="agent", content=response, timestamp=timestamp)
            except Exception as e:
                logger.debug("Failed to log response to message_log: %s", e)

            # Push response to chat UI via WebSocket
            try:
                from infrastructure.ws_manager.handler import ws_manager
                asyncio.create_task(
                    ws_manager.broadcast(
                        "timmy_response",
                        {
                            "task_id": task.id,
                            "response": response,
                        },
                    )
                )
            except Exception as e:
                logger.debug("Failed to push response via WS: %s", e)

            return response
        except Exception as e:
            logger.error("Chat response failed: %s", e)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(e, source="chat_response_handler")
            except Exception:
                pass
            return f"Error: {str(e)}"

    def handle_thought(task):
        from timmy.thinking import thinking_engine
        try:
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(
                thinking_engine.think_once(), loop
            )
            result = future.result(timeout=120)
            return str(result) if result else "Thought completed"
        except Exception as e:
            logger.error("Thought processing failed: %s", e)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(e, source="thought_handler")
            except Exception:
                pass
            return f"Error: {str(e)}"

    def handle_task_request(task):
        try:
            now = datetime.now()
            context = (
                f"[System: Current date/time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}]\n"
                f"[System: You have been assigned a task from the queue. "
                f"Complete it and provide your response.]\n\n"
                f"Task: {task.title}\n"
            )
            if task.description and task.description != task.title:
                context += f"Details: {task.description}\n"

            response = timmy_chat(context)

            try:
                from infrastructure.ws_manager.handler import ws_manager
                asyncio.create_task(
                    ws_manager.broadcast(
                        "task_response",
                        {
                            "task_id": task.id,
                            "response": response,
                        },
                    )
                )
            except Exception as e:
                logger.debug("Failed to push task response via WS: %s", e)

            return response
        except Exception as e:
            logger.error("Task request processing failed: %s", e)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(e, source="task_request_handler")
            except Exception:
                pass
            return f"Error: {str(e)}"

    # Register handlers for all known task types
    task_processor.register_handler("chat_response", handle_chat_response)
    task_processor.register_handler("thought", handle_thought)
    task_processor.register_handler("internal", handle_thought)
    task_processor.register_handler("bug_report", handle_bug_report)
    task_processor.register_handler("task_request", handle_task_request)
    task_processor.register_handler("escalation", handle_task_request)
    task_processor.register_handler("external", handle_task_request)

    # ── Reconcile zombie tasks from previous crash ──
    zombie_count = task_processor.reconcile_zombie_tasks()
    if zombie_count:
        logger.info("Recycled %d zombie task(s) back to approved", zombie_count)

    # ── Re-approve tasks backlogged due to missing handlers ──
    stale = list_tasks(status=TaskStatus.BACKLOGGED, assigned_to="timmy")
    requeued = 0
    for t in stale:
        if t.backlog_reason and "No handler for task type" in t.backlog_reason:
            update_task_status(t.id, TaskStatus.APPROVED, result=None)
            requeued += 1
    if requeued:
        logger.info("Re-queued %d task(s) that were backlogged due to missing handlers", requeued)

    # ── Startup drain: iterate through all pending tasks immediately ──
    logger.info("Draining task queue on startup...")
    try:
        summary = await task_processor.drain_queue()
        if summary["processed"] or summary["backlogged"]:
            logger.info(
                "Startup drain: %d processed, %d backlogged, %d skipped, %d failed",
                summary["processed"],
                summary["backlogged"],
                summary["skipped"],
                summary["failed"],
            )

            # Notify via WebSocket so the dashboard updates
            try:
                from infrastructure.ws_manager.handler import ws_manager

                asyncio.create_task(
                    ws_manager.broadcast_json(
                        {
                            "type": "task_event",
                            "event": "startup_drain_complete",
                            "summary": summary,
                        }
                    )
                )
            except Exception:
                pass
    except Exception as exc:
        logger.error("Startup drain failed: %s", exc)
        try:
            from infrastructure.error_capture import capture_error
            capture_error(exc, source="task_processor_startup")
        except Exception:
            pass

    # ── Steady-state: poll for new tasks ──
    logger.info("Task processor entering steady-state loop")
    await task_processor.run_loop(interval_seconds=3.0)


async def _spawn_persona_agents_background() -> None:
    """Background task: spawn persona agents without blocking startup."""
    from swarm.coordinator import coordinator as swarm_coordinator
    
    await asyncio.sleep(1)  # Let server fully start
    
    if os.environ.get("TIMMY_TEST_MODE") != "1":
        logger.info("Auto-spawning persona agents: Echo, Forge, Seer...")
        try:
            swarm_coordinator.spawn_persona("echo", agent_id="persona-echo")
            swarm_coordinator.spawn_persona("forge", agent_id="persona-forge")
            swarm_coordinator.spawn_persona("seer", agent_id="persona-seer")
            logger.info("Persona agents spawned successfully")
        except Exception as exc:
            logger.error("Failed to spawn persona agents: %s", exc)


async def _bootstrap_mcp_background() -> None:
    """Background task: bootstrap MCP tools without blocking startup."""
    from mcp.bootstrap import auto_bootstrap
    
    await asyncio.sleep(0.5)  # Let server start
    
    try:
        registered = auto_bootstrap()
        if registered:
            logger.info("MCP auto-bootstrap: %d tools registered", len(registered))
    except Exception as exc:
        logger.warning("MCP auto-bootstrap failed: %s", exc)


async def _start_chat_integrations_background() -> None:
    """Background task: start chat integrations without blocking startup."""
    from integrations.telegram_bot.bot import telegram_bot
    from integrations.chat_bridge.vendors.discord import discord_bot
    from integrations.chat_bridge.registry import platform_registry

    await asyncio.sleep(0.5)

    # Register Discord in the platform registry
    platform_registry.register(discord_bot)
    
    if settings.telegram_token:
        try:
            await telegram_bot.start()
            logger.info("Telegram bot started")
        except Exception as exc:
            logger.warning("Failed to start Telegram bot: %s", exc)
    else:
        logger.debug("Telegram: no token configured, skipping")

    if settings.discord_token or discord_bot.load_token():
        try:
            await discord_bot.start()
            logger.info("Discord bot started")
        except Exception as exc:
            logger.warning("Failed to start Discord bot: %s", exc)
    else:
        logger.debug("Discord: no token configured, skipping")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with non-blocking startup."""
    
    # Create all background tasks without waiting for them
    briefing_task = asyncio.create_task(_briefing_scheduler())
    
    # Run swarm recovery first (offlines all stale agents)
    from swarm.coordinator import coordinator as swarm_coordinator
    swarm_coordinator.initialize()
    rec = swarm_coordinator._recovery_summary
    if rec["tasks_failed"] or rec["agents_offlined"]:
        logger.info(
            "Swarm recovery on startup: %d task(s) → FAILED, %d agent(s) → offline",
            rec["tasks_failed"],
            rec["agents_offlined"],
        )

    # Register Timmy AFTER recovery sweep so status sticks as "idle"
    from swarm import registry as swarm_registry
    swarm_registry.register(
        name="Timmy",
        capabilities="chat,reasoning,research,planning",
        agent_id="timmy",
    )

    # Spawn persona agents in background
    persona_task = asyncio.create_task(_spawn_persona_agents_background())

    # Log system startup event
    try:
        from swarm.event_log import log_event, EventType
        log_event(
            EventType.SYSTEM_INFO,
            source="coordinator",
            data={"message": "Timmy Time system started"},
        )
    except Exception:
        pass

    # Bootstrap MCP tools in background
    mcp_task = asyncio.create_task(_bootstrap_mcp_background())

    # Register OpenFang vendor tools (if enabled)
    if settings.openfang_enabled:
        try:
            from infrastructure.openfang.tools import register_openfang_tools

            count = register_openfang_tools()
            logger.info("OpenFang: registered %d vendor tools", count)
        except Exception as exc:
            logger.warning("OpenFang tool registration failed: %s", exc)

    # Initialize Spark Intelligence engine
    from spark.engine import spark_engine
    if spark_engine.enabled:
        logger.info("Spark Intelligence active — event capture enabled")

    # Start thinking thread if enabled
    thinking_task = None
    if settings.thinking_enabled and os.environ.get("TIMMY_TEST_MODE") != "1":
        thinking_task = asyncio.create_task(_thinking_loop())
        logger.info(
            "Default thinking thread started (interval: %ds)",
            settings.thinking_interval_seconds,
        )

    # Start task processor if not in test mode
    task_processor_task = None
    if os.environ.get("TIMMY_TEST_MODE") != "1":
        task_processor_task = asyncio.create_task(_task_processor_loop())
        logger.info("Task queue processor started")

    # Start chat integrations in background
    chat_task = asyncio.create_task(_start_chat_integrations_background())

    logger.info("✓ Timmy Time dashboard ready for requests")

    yield

    # Cleanup on shutdown
    from integrations.telegram_bot.bot import telegram_bot
    from integrations.chat_bridge.vendors.discord import discord_bot

    await discord_bot.stop()
    await telegram_bot.stop()
    
    for task in [thinking_task, task_processor_task, briefing_task, persona_task, mcp_task, chat_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Timmy Time — Mission Control",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = PROJECT_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Global templates instance
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# Include routers
app.include_router(health_router)
app.include_router(agents_router)
app.include_router(swarm_router)
app.include_router(swarm_internal_router)
app.include_router(marketplace_router)
app.include_router(voice_router)
app.include_router(mobile_router)
app.include_router(briefing_router)
app.include_router(telegram_router)
app.include_router(tools_router)
app.include_router(spark_router)
app.include_router(creative_router)
app.include_router(discord_router)
app.include_router(events_router)
app.include_router(ledger_router)
app.include_router(memory_router)
app.include_router(router_status_router)
app.include_router(upgrades_router)
app.include_router(work_orders_router)
app.include_router(tasks_router)
app.include_router(scripture_router)
app.include_router(self_coding_router)
app.include_router(self_modify_router)
app.include_router(hands_router)
app.include_router(grok_router)
app.include_router(models_router)
app.include_router(models_api_router)
app.include_router(chat_api_router)
app.include_router(thinking_router)
app.include_router(bugs_router)
app.include_router(cascade_router)


@app.websocket("/ws")
async def ws_redirect(websocket: WebSocket):
    """Catch stale /ws connections and close cleanly.

    Before PR #82, frontend code connected to /ws which never existed as
    an endpoint.  Stale browser tabs retry forever, spamming 403 errors.
    Accept the connection and immediately close with a policy-violation
    code so the client stops retrying.

    websockets 16.0 dropped the legacy ``transfer_data_task`` attribute,
    so calling ``websocket.close()`` after accept triggers an
    AttributeError.  Use the raw ASGI send instead.
    """
    await websocket.accept()
    try:
        await websocket.close(code=1008, reason="Use /swarm/live instead")
    except AttributeError:
        # websockets >= 16.0 — close via raw ASGI message
        await websocket.send({"type": "websocket.close", "code": 1008})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/shortcuts/setup")
async def shortcuts_setup():
    """Siri Shortcuts setup guide."""
    from integrations.shortcuts.siri import get_setup_guide

    return get_setup_guide()
