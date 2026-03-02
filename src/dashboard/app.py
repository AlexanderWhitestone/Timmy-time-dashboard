"""Optimized dashboard app with improved async handling and non-blocking startup.

Key improvements:
1. Background tasks use asyncio.create_task() to avoid blocking startup
2. Chat integrations start in background
3. All startup operations complete quickly
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.dashboard.routes.agents import router as agents_router
from src.dashboard.routes.health import router as health_router
from src.dashboard.routes.marketplace import router as marketplace_router
from src.dashboard.routes.voice import router as voice_router
from src.dashboard.routes.mobile import router as mobile_router
from src.dashboard.routes.briefing import router as briefing_router
from src.dashboard.routes.telegram import router as telegram_router
from src.dashboard.routes.tools import router as tools_router
from src.dashboard.routes.spark import router as spark_router
from src.dashboard.routes.discord import router as discord_router
from src.dashboard.routes.memory import router as memory_router
from src.dashboard.routes.router import router as router_status_router
from src.dashboard.routes.grok import router as grok_router
from src.dashboard.routes.models import router as models_router
from src.dashboard.routes.models import api_router as models_api_router
from src.dashboard.routes.chat_api import router as chat_api_router
from src.dashboard.routes.thinking import router as thinking_router
from src.dashboard.routes.calm import router as calm_router
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

        await asyncio.sleep(_BRIEFING_INTERVAL_HOURS * 3600)


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

    # If Discord isn't connected yet, start a watcher that polls for the
    # token to appear in the environment or .env file.
    if discord_bot.state.name != "CONNECTED":
        asyncio.create_task(_discord_token_watcher())


async def _discord_token_watcher() -> None:
    """Poll for DISCORD_TOKEN appearing in env or .env and auto-start Discord bot."""
    from integrations.chat_bridge.vendors.discord import discord_bot

    while True:
        await asyncio.sleep(30)

        if discord_bot.state.name == "CONNECTED":
            return  # Already running — stop watching

        # 1. Check live environment variable
        token = os.environ.get("DISCORD_TOKEN", "")

        # 2. Re-read .env file for hot-reload
        if not token:
            try:
                from dotenv import dotenv_values

                env_path = Path(settings.repo_root) / ".env"
                if env_path.exists():
                    vals = dotenv_values(env_path)
                    token = vals.get("DISCORD_TOKEN", "")
            except ImportError:
                pass  # python-dotenv not installed

        # 3. Check state file (written by /discord/setup)
        if not token:
            token = discord_bot.load_token() or ""

        if token:
            try:
                success = await discord_bot.start(token=token)
                if success:
                    logger.info("Discord bot auto-started (token detected)")
                    return  # Done — stop watching
            except Exception as exc:
                logger.warning("Discord auto-start failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with non-blocking startup."""

    # Create all background tasks without waiting for them
    briefing_task = asyncio.create_task(_briefing_scheduler())

    # Initialize Spark Intelligence engine
    from spark.engine import spark_engine
    if spark_engine.enabled:
        logger.info("Spark Intelligence active — event capture enabled")

    # Start chat integrations in background
    chat_task = asyncio.create_task(_start_chat_integrations_background())

    logger.info("✓ Timmy Time dashboard ready for requests")

    yield

    # Cleanup on shutdown
    from integrations.telegram_bot.bot import telegram_bot
    from integrations.chat_bridge.vendors.discord import discord_bot

    await discord_bot.stop()
    await telegram_bot.stop()

    for task in [briefing_task, chat_task]:
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


def _get_cors_origins() -> list[str]:
    """Get CORS origins from settings, with sensible defaults."""
    origins = settings.cors_origins
    if settings.debug and origins == ["*"]:
        return [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
    return origins


async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net; "
        "font-src 'self' fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


app.middleware("http")(add_security_headers)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.local", "testserver"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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
app.include_router(marketplace_router)
app.include_router(voice_router)
app.include_router(mobile_router)
app.include_router(briefing_router)
app.include_router(telegram_router)
app.include_router(tools_router)
app.include_router(spark_router)
app.include_router(discord_router)
app.include_router(memory_router)
app.include_router(router_status_router)
app.include_router(grok_router)
app.include_router(models_router)
app.include_router(models_api_router)
app.include_router(chat_api_router)
app.include_router(thinking_router)
app.include_router(calm_router)
app.include_router(cascade_router)


@app.websocket("/ws")
async def ws_redirect(websocket: WebSocket):
    """Catch stale /ws connections and close cleanly."""
    await websocket.accept()
    try:
        await websocket.close(code=1008, reason="Deprecated endpoint")
    except AttributeError:
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
