import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
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

    # Console handler (existing behavior)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.addHandler(console)

    # Rotating file handler for errors
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
    """Background task: regenerate Timmy's briefing every 6 hours.

    Runs once at startup (after a short delay to let the server settle),
    then on a 6-hour cadence.  Skips generation if a fresh briefing already
    exists (< 30 min old).
    """
    from timmy.briefing import engine as briefing_engine
    from infrastructure.notifications.push import notify_briefing_ready

    await asyncio.sleep(2)  # Let server finish starting before first run

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
    """Background task: Timmy's default thinking thread.

    Instead of thinking directly, this creates thought tasks in the queue
    for the task processor to handle. This ensures all of Timmy's work
    goes through the unified task system.
    """
    from swarm.task_queue.models import create_task
    from datetime import datetime

    await asyncio.sleep(10)  # Let server finish starting before first thought

    while True:
        try:
            # Create a thought task instead of thinking directly
            now = datetime.now()
            create_task(
                title=f"Thought: {now.strftime('%A %B %d, %I:%M %p')}",
                description="Continue thinking about your existence, recent events, scripture, creative ideas, or a previous thread of thought.",
                assigned_to="timmy",
                created_by="timmy",  # Self-generated
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


async def _task_processor_loop() -> None:
    """Background task: Timmy's task queue processor.

    On startup, drains all pending/approved tasks immediately — iterating
    through the queue and processing what can be handled, backlogging what
    can't.  Then enters the steady-state polling loop.
    """
    from swarm.task_processor import task_processor
    from swarm.task_queue.models import update_task_status, TaskStatus
    from timmy.session import chat as timmy_chat
    from datetime import datetime
    import json
    import asyncio

    await asyncio.sleep(5)  # Let server finish starting

    def handle_chat_response(task):
        """Handler for chat_response tasks - calls Timmy and returns response."""
        try:
            now = datetime.now()
            context = f"[System: Current date/time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}]\n\n"
            response = timmy_chat(context + task.description)

            # Push response to user via WebSocket
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
        """Handler for thought tasks - Timmy's internal thinking."""
        from timmy.thinking import thinking_engine

        try:
            result = thinking_engine.think_once()
            return str(result) if result else "Thought completed"
        except Exception as e:
            logger.error("Thought processing failed: %s", e)
            try:
                from infrastructure.error_capture import capture_error
                capture_error(e, source="thought_handler")
            except Exception:
                pass
            return f"Error: {str(e)}"

    def handle_bug_report(task):
        """Handler for bug_report tasks - acknowledge and mark completed."""
        return f"Bug report acknowledged: {task.title}"

    # Register handlers
    task_processor.register_handler("chat_response", handle_chat_response)
    task_processor.register_handler("thought", handle_thought)
    task_processor.register_handler("internal", handle_thought)
    task_processor.register_handler("bug_report", handle_bug_report)

    # ── Startup drain: iterate through all pending tasks immediately ──
    logger.info("Draining task queue on startup…")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_briefing_scheduler())

    # Register Timmy in the swarm registry so it shows up alongside other agents
    from swarm import registry as swarm_registry

    swarm_registry.register(
        name="Timmy",
        capabilities="chat,reasoning,research,planning",
        agent_id="timmy",
    )

    # Log swarm recovery summary (reconciliation ran during coordinator init)
    from swarm.coordinator import coordinator as swarm_coordinator

    rec = swarm_coordinator._recovery_summary
    if rec["tasks_failed"] or rec["agents_offlined"]:
        logger.info(
            "Swarm recovery on startup: %d task(s) → FAILED, %d agent(s) → offline",
            rec["tasks_failed"],
            rec["agents_offlined"],
        )

    # Auto-spawn persona agents for a functional swarm (Echo, Forge, Seer)
    # Skip auto-spawning in test mode to avoid test isolation issues
    if os.environ.get("TIMMY_TEST_MODE") != "1":
        logger.info("Auto-spawning persona agents: Echo, Forge, Seer...")
        try:
            swarm_coordinator.spawn_persona("echo", agent_id="persona-echo")
            swarm_coordinator.spawn_persona("forge", agent_id="persona-forge")
            swarm_coordinator.spawn_persona("seer", agent_id="persona-seer")
            logger.info("Persona agents spawned successfully")
        except Exception as exc:
            logger.error("Failed to spawn persona agents: %s", exc)

    # Log system startup event so the Events page is never empty
    try:
        from swarm.event_log import log_event, EventType

        log_event(
            EventType.SYSTEM_INFO,
            source="coordinator",
            data={"message": "Timmy Time system started"},
        )
    except Exception:
        pass

    # Auto-bootstrap MCP tools
    from mcp.bootstrap import auto_bootstrap, get_bootstrap_status

    try:
        registered = auto_bootstrap()
        if registered:
            logger.info("MCP auto-bootstrap: %d tools registered", len(registered))
    except Exception as exc:
        logger.warning("MCP auto-bootstrap failed: %s", exc)

    # Initialise Spark Intelligence engine
    from spark.engine import spark_engine

    if spark_engine.enabled:
        logger.info("Spark Intelligence active — event capture enabled")

    # Start Timmy's default thinking thread (skip in test mode)
    thinking_task = None
    if settings.thinking_enabled and os.environ.get("TIMMY_TEST_MODE") != "1":
        thinking_task = asyncio.create_task(_thinking_loop())
        logger.info(
            "Default thinking thread started (interval: %ds)",
            settings.thinking_interval_seconds,
        )

    # Start Timmy's task queue processor (skip in test mode)
    task_processor_task = None
    if os.environ.get("TIMMY_TEST_MODE") != "1":
        task_processor_task = asyncio.create_task(_task_processor_loop())
        logger.info("Task queue processor started")

    # Auto-start chat integrations (skip silently if unconfigured)
    from integrations.telegram_bot.bot import telegram_bot
    from integrations.chat_bridge.vendors.discord import discord_bot
    from integrations.chat_bridge.registry import platform_registry

    platform_registry.register(discord_bot)

    if settings.telegram_token:
        await telegram_bot.start()
    else:
        logger.debug("Telegram: no token configured, skipping")

    if settings.discord_token or discord_bot.load_token():
        await discord_bot.start()
    else:
        logger.debug("Discord: no token configured, skipping")

    yield

    await discord_bot.stop()
    await telegram_bot.stop()
    if thinking_task:
        thinking_task.cancel()
        try:
            await thinking_task
        except asyncio.CancelledError:
            pass
    if task_processor_task:
        task_processor_task.cancel()
        try:
            await task_processor_task
        except asyncio.CancelledError:
            pass
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Timmy Time — Mission Control",
    version="1.0.0",
    lifespan=lifespan,
    # Docs disabled unless DEBUG=true in env / .env
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

# Serve uploaded chat attachments (created lazily by /api/upload)
_uploads_dir = PROJECT_ROOT / "data" / "chat-uploads"
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads",
    StaticFiles(directory=str(_uploads_dir)),
    name="uploads",
)

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
app.include_router(self_coding_router)
app.include_router(self_modify_router)
app.include_router(events_router)
app.include_router(ledger_router)
app.include_router(memory_router)
app.include_router(router_status_router)
app.include_router(upgrades_router)
app.include_router(work_orders_router)
app.include_router(tasks_router)
app.include_router(scripture_router)
app.include_router(hands_router)
app.include_router(grok_router)
app.include_router(models_router)
app.include_router(models_api_router)
app.include_router(chat_api_router)
app.include_router(thinking_router)
app.include_router(cascade_router)
app.include_router(bugs_router)


# ── Error capture middleware ──────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.responses import JSONResponse


class ErrorCaptureMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and feed them into the error feedback loop."""

    async def dispatch(self, request: StarletteRequest, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(
                "Unhandled exception on %s %s: %s",
                request.method, request.url.path, exc,
            )
            try:
                from infrastructure.error_capture import capture_error
                capture_error(
                    exc,
                    source="http_middleware",
                    context={
                        "method": request.method,
                        "path": request.url.path,
                        "query": str(request.query_params),
                    },
                )
            except Exception:
                pass  # Never crash the middleware itself
            raise  # Re-raise so FastAPI's default handler returns 500


app.add_middleware(ErrorCaptureMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Safety net for uncaught exceptions."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    try:
        from infrastructure.error_capture import capture_error
        capture_error(exc, source="exception_handler", context={"path": str(request.url)})
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/shortcuts/setup")
async def shortcuts_setup():
    """Siri Shortcuts setup guide."""
    from integrations.shortcuts.siri import get_setup_guide

    return get_setup_guide()
