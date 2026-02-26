import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from dashboard.routes.agents import router as agents_router
from dashboard.routes.health import router as health_router
from dashboard.routes.mobile_test import router as mobile_test_router
from dashboard.routes.swarm import router as swarm_router
from dashboard.routes.marketplace import router as marketplace_router
from dashboard.routes.voice import router as voice_router
from dashboard.routes.voice_enhanced import router as voice_enhanced_router
from dashboard.routes.mobile import router as mobile_router
from dashboard.routes.swarm_ws import router as swarm_ws_router
from dashboard.routes.briefing import router as briefing_router
from dashboard.routes.telegram import router as telegram_router
from dashboard.routes.swarm_internal import router as swarm_internal_router
from dashboard.routes.tools import router as tools_router
from dashboard.routes.spark import router as spark_router
from dashboard.routes.creative import router as creative_router
from dashboard.routes.discord import router as discord_router
from dashboard.routes.self_modify import router as self_modify_router
from router.api import router as cascade_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
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
    from notifications.push import notify_briefing_ready

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

        await asyncio.sleep(_BRIEFING_INTERVAL_HOURS * 3600)


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

    # Initialise Spark Intelligence engine
    from spark.engine import spark_engine
    if spark_engine.enabled:
        logger.info("Spark Intelligence active — event capture enabled")

    # Auto-start Telegram bot if a token is configured
    from telegram_bot.bot import telegram_bot
    await telegram_bot.start()

    # Auto-start Discord bot and register in platform registry
    from chat_bridge.vendors.discord import discord_bot
    from chat_bridge.registry import platform_registry
    platform_registry.register(discord_bot)
    await discord_bot.start()

    yield

    await discord_bot.stop()
    await telegram_bot.stop()
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

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

app.include_router(health_router)
app.include_router(agents_router)
app.include_router(mobile_test_router)
app.include_router(swarm_router)
app.include_router(marketplace_router)
app.include_router(voice_router)
app.include_router(voice_enhanced_router)
app.include_router(mobile_router)
app.include_router(swarm_ws_router)
app.include_router(briefing_router)
app.include_router(telegram_router)
app.include_router(swarm_internal_router)
app.include_router(tools_router)
app.include_router(spark_router)
app.include_router(creative_router)
app.include_router(discord_router)
app.include_router(self_modify_router)
app.include_router(cascade_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/shortcuts/setup")
async def shortcuts_setup():
    """Siri Shortcuts setup guide."""
    from shortcuts.siri import get_setup_guide
    return get_setup_guide()
