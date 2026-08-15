from typing import Literal

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def _webhook_mode_needs_a_reachable_url(self):
        """Refuse to start in a configuration where the bot cannot hear anything.

        Telegram only delivers updates to a public HTTPS URL. Pointed at
        localhost or plain http, the app registers a webhook that can never
        fire: /start gets no reply, nothing is written to the database, and
        nothing in the logs says why. That silence is the exact failure this
        setting was made explicit to avoid, so it is an error, with the fix in
        the message.
        """
        if self.bot_mode == "webhook":
            host = self.base_url.strip().lower()
            unreachable = (
                not host.startswith("https://")
                or "localhost" in host
                or "127.0.0.1" in host
                or "0.0.0.0" in host  # noqa: S104 -- matching a string, not binding
            )
            if unreachable:
                raise ValueError(
                    f"BOT_MODE=webhook needs a public HTTPS BASE_URL that Telegram "
                    f"can reach; got {self.base_url!r}. For local development set "
                    f"BOT_MODE=polling in your .env."
                )
        return self


settings = Settings()
