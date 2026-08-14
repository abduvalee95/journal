import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth as auth_api
from app.api import lessons as lessons_api
from app.bot.handlers import confirm as confirm_handler
from app.bot.handlers import start as start_handler
from app.bot.handlers import voice as voice_handler
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.services.outbox import run_outbox

logger = logging.getLogger(__name__)

bot = Bot(token=settings.bot_token)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(start_handler.router)
dp.include_router(voice_handler.router)
dp.include_router(confirm_handler.router)

WEBHOOK_PATH = "/webhook/telegram"


@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = None
    use_webhook = settings.bot_mode == "webhook"

    if use_webhook:
        webhook_url = f"{settings.base_url}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret)
            logger.info("Telegram webhook registered at %s", webhook_url)
        except Exception:
            logger.exception("Failed to register Telegram webhook at %s", webhook_url)
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Failed to delete Telegram webhook before polling")
        # In local dev without public HTTPS, use long polling
        polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        logger.info("Telegram bot running in Long Polling mode for local dev")

    outbox_task = asyncio.create_task(run_outbox(bot))
    yield

    outbox_task.cancel()
    if polling_task:
        polling_task.cancel()

    try:
        await outbox_task
    except asyncio.CancelledError:
        pass

    if polling_task:
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    if use_webhook:
        try:
            await bot.delete_webhook()
        except Exception:
            logger.exception("Failed to delete Telegram webhook")

    try:
        await bot.session.close()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# Only the Mini App origin, plus the Vite dev server. A wildcard would let any
# page on the internet call the API with a leaked token, and it contradicted
# what the Caddyfile, .env.example and docs/deploy.md all say happens here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o for o in (
            settings.miniapp_url,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ) if o
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Telegram-Bot-Api-Secret-Token"],
)

app.include_router(auth_api.router)
app.include_router(lessons_api.router)


@app.get("/")
async def root():
    return {
        "name": "Ustoz Jurnali API",
        "status": "online",
        "health": "/api/health",
    }


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Receive one Telegram update.

    The shared secret is checked from the header only -- it used to also sit in
    the URL path, which put it into every proxy access log on disk.

    Anything malformed returns 200 rather than raising: a 500 makes Telegram
    redeliver the same update indefinitely, so one poison payload would loop
    forever.
    """
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(token, settings.webhook_secret):
        return Response(status_code=403)
    try:
        data = await request.json()
        update = Update.model_validate(data)
    except Exception:
        logger.exception("Discarding malformed Telegram update")
        return Response()
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Telegram update handler failed")
    return Response()


@app.get("/api/health")
async def health():
    """Liveness + database reachability.

    A process that is up but cannot reach its database is down as far as the
    teacher is concerned, and UptimeRobot only ever sees this endpoint.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed to reach the database")
        return Response(
            content='{"status":"error","database":"unreachable"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ok", "database": "ok"}
