import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from app.config import settings
from app.bot.handlers import start as start_handler
from app.bot.handlers import voice as voice_handler
from app.bot.handlers import confirm as confirm_handler
from app.api import auth as auth_api
from app.api import lessons as lessons_api
from app.services.outbox import run_outbox

logger = logging.getLogger(__name__)

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

bot = Bot(token=settings.bot_token)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(start_handler.router)
dp.include_router(voice_handler.router)
dp.include_router(confirm_handler.router)


def _should_use_webhook() -> bool:
    url = (settings.base_url or "").strip()
    return (
        url.startswith("https://")
        and "domain.uz" not in url
        and "localhost" not in url
        and "127.0.0.1" not in url
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = None
    use_webhook = _should_use_webhook()

    if use_webhook:
        webhook_url = f"{settings.base_url}/webhook/telegram/{settings.webhook_secret}"
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

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
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
        "docs": "/docs",
        "health": "/api/health",
    }


@app.post("/webhook/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.webhook_secret:
        return Response(status_code=403)
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != settings.webhook_secret:
        return Response(status_code=403)
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return Response()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
