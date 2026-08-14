"""Environment for the test suite.

Every variable `Settings` requires is set here, before `app.config` is first
imported, so `pytest` runs on a clean checkout with no `.env` present -- which
is what CI has. `setdefault` throughout, so a developer's own environment still
wins locally.

DATABASE_URL matters as much as the secrets: `app.db.session` builds the engine
at import time, so without it a test that forgets to override `get_session`
would write to the real development database.
"""
import os

os.environ.setdefault("BOT_TOKEN", "123456789:TEST-not-a-real-telegram-bot-token")
os.environ.setdefault("TEACHER_TELEGRAM_ID", "424242")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-used-in-production")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-32-chars-long")
os.environ.setdefault("BASE_URL", "https://api.test.invalid")
os.environ.setdefault("MINIAPP_URL", "https://miniapp.test.invalid")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ELEVENLABS_API_KEY", "test-elevenlabs-key")
os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("LLM_MODEL", "claude-haiku-4-5-20251001")
os.environ.setdefault("BOT_MODE", "polling")
