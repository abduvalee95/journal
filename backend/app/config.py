from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment / `.env`.

    Everything the app cannot function without is required. Booting with a
    missing secret and failing later, in the field, is strictly worse than
    refusing to start: an empty `webhook_secret` registers the webhook at
    `/webhook/telegram/`, which is unroutable, so the bot goes silently dead
    with nothing in the logs to explain it.
    """

    bot_token: str
    webhook_secret: str = Field(min_length=16)
    teacher_telegram_id: int
    base_url: str
    miniapp_url: str
    jwt_secret: str = Field(min_length=16)
    database_url: str = "sqlite+aiosqlite:///./data/journal.db"

    # Whether to register a Telegram webhook or long-poll. Explicit, because
    # inferring it from the shape of BASE_URL silently picked the wrong mode
    # for any host whose name happened to match the placeholder.
    bot_mode: Literal["webhook", "polling"] = "webhook"

    elevenlabs_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"

    # "auto" keeps inferring the provider from the key prefix / model name so
    # existing deployments are unaffected; pin it to make the choice explicit
    # (and to exercise a specific provider's branch from a test).
    llm_provider: Literal["auto", "anthropic", "groq", "gemini"] = "auto"
    asr_provider: Literal["auto", "elevenlabs", "groq"] = "auto"

    # Cap on model-authored text before it is stored or sent. A Telegram
    # message is limited to 4096 characters; a single oversized field would
    # otherwise make sendMessage fail and the report never arrive.
    max_summary_chars: int = 1500
    max_note_chars: int = 400

    model_config = SettingsConfigDict(env_file=[".env", "../.env"], extra="ignore")


settings = Settings()
