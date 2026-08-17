"""Settings must refuse configurations in which the bot cannot work.

The failure this guards against is silent: pointed at a URL Telegram cannot
reach, the app starts, registers a webhook that never fires, answers /start
with nothing, writes nothing to the database, and logs no reason.
"""
import pytest
from pydantic import ValidationError

from app.config import Settings

# conftest exports these for the rest of the suite, and pydantic-settings
# reads the process environment -- so without clearing them "not provided"
# tests would silently be testing the conftest values instead.
_APP_ENV_VARS = (
    "BOT_TOKEN", "WEBHOOK_SECRET", "TEACHER_TELEGRAM_ID", "BASE_URL",
    "MINIAPP_URL", "JWT_SECRET", "DATABASE_URL", "BOT_MODE",
    "ELEVENLABS_API_KEY", "LLM_API_KEY", "LLM_MODEL",
    "LLM_PROVIDER", "ASR_PROVIDER",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


BASE = {
    "bot_token": "123456789:TEST-token",
    "teacher_telegram_id": 424242,
    "jwt_secret": "a-jwt-secret-of-adequate-length",
    "webhook_secret": "a-webhook-secret-long-enough",
    "miniapp_url": "https://miniapp.example.test",
    # _env_file=None so a developer's real .env cannot influence the result.
    "_env_file": None,
}


def _settings(**overrides):
    return Settings(**{**BASE, **overrides})


@pytest.mark.parametrize("base_url", [
    "http://localhost:8000",
    "https://localhost:8000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:8000",
    "http://api.example.test",       # plain http is not reachable by Telegram
])
def test_webhook_mode_refuses_a_url_telegram_cannot_reach(base_url):
    with pytest.raises(ValidationError) as exc:
        _settings(bot_mode="webhook", base_url=base_url)
    # The message has to carry the fix, because the person hitting this is
    # looking at a bot that simply says nothing.
    assert "BOT_MODE=polling" in str(exc.value)


def test_webhook_mode_accepts_a_public_https_url():
    s = _settings(bot_mode="webhook", base_url="https://api.example.test")
    assert s.bot_mode == "webhook"


def test_polling_mode_does_not_care_about_the_url():
    """Local development has no public hostname; that is the whole point."""
    s = _settings(bot_mode="polling", base_url="http://localhost:8000")
    assert s.bot_mode == "polling"


def test_webhook_is_the_default_so_production_needs_no_extra_setting():
    s = _settings(base_url="https://api.example.test")
    assert s.bot_mode == "webhook"


@pytest.mark.parametrize("field", ["webhook_secret", "base_url", "miniapp_url"])
def test_required_settings_are_required(field):
    """These were briefly optional with empty-string defaults, which let the
    app boot into a state where nothing worked."""
    values = {k: v for k, v in BASE.items() if k != field}
    values.setdefault("base_url", "https://api.example.test")
    values.pop(field, None)
    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize("field", ["jwt_secret", "webhook_secret"])
def test_secrets_must_not_be_trivially_short(field):
    with pytest.raises(ValidationError):
        _settings(base_url="https://api.example.test", **{field: "short"})
