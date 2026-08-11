import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from app.config import settings
from app.bot.handlers import start as start_handler
from app.api import auth as auth_api

logger = logging.getLogger(__name__)

bot = Bot(token=settings.bot_token)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(start_handler.router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{settings.base_url}/webhook/telegram/{settings.webhook_secret}"
    try:
        await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret)
    except Exception:
        logger.exception("Failed to register Telegram webhook at %s", webhook_url)
    yield
    try:
        await bot.delete_webhook()
    except Exception:
        logger.exception("Failed to delete Telegram webhook")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.miniapp_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_api.router)


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
