import os

# `backend/.env` intentionally keeps a non-functional placeholder BOT_TOKEN for local
# dev so nothing ever talks to the real bot by accident. That placeholder does not
# match Telegram's `<digits>:<rest>` token shape, so aiogram's `Bot(token=...)` raises
# `TokenValidationError` at import time. Override with a validly-shaped (but still
# fake) token for the test process only -- this never touches the real .env file and
# only applies if no BOT_TOKEN is already exported in the environment.
os.environ.setdefault("BOT_TOKEN", "123456789:TEST-not-a-real-telegram-bot-token")
