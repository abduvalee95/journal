# Ustoz Jurnali

A Telegram bot and Mini App for one language teacher: attendance, 1–5 grades,
and per-student lesson reports. After a class the teacher sends a voice note;
ASR and an LLM turn it into a draft the teacher reviews in the Mini App, and
each student receives their own report as a Telegram message.

Design spec: [`docs/superpowers/specs/2026-08-11-ustoz-jurnali-design.md`](docs/superpowers/specs/2026-08-11-ustoz-jurnali-design.md).
Deployment runbook: [`docs/deploy.md`](docs/deploy.md).
Most recent engineering review: [`docs/audit-2026-08-14.md`](docs/audit-2026-08-14.md).

UI language is Uzbek in Cyrillic script. Times are `Asia/Bishkek`.

## What runs where

| Piece | Where | Notes |
|---|---|---|
| FastAPI + aiogram bot + outbox worker | VPS, one container | one process, `--workers 1` |
| TLS / reverse proxy | VPS, Caddy | automatic Let's Encrypt |
| SQLite database | VPS, `./data/journal.db` | bind mount |
| Mini App (React + Vite) | Vercel | static build from `miniapp/` |

The bot, the HTTP API and the outbox loop are deliberately one process: the
outbox worker and the webhook registration both live in the FastAPI lifespan,
so a second worker would send every student their report twice.

**The backend does not run serverless.** See `docs/deploy.md` §0.

## Running the tests

Both suites run on a clean checkout with no `.env` — that is what CI does.

```bash
# backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                       # 152 tests
pytest -q --cov=app --cov-report=term-missing
ruff check .

# frontend
cd miniapp
npm ci
npm test                        # 126 tests
npm run typecheck
npm run lint
```

`mypy` is configured in `backend/pyproject.toml` but is **not** a CI gate yet:
the models still use SQLAlchemy's legacy `Column()` style, so every attribute
types as `Column[str]` rather than `str` and the run is ~98 false positives.
Migrating the models to `Mapped[]` is what makes it meaningful.

`ruff format` is likewise available but not enforced — adopting it is a
one-shot reformat of the whole tree, which is worth its own commit.

## Local development

```bash
cp .env.example .env            # fill in BOT_TOKEN, TEACHER_TELEGRAM_ID, secrets
```

Set `BOT_MODE=polling` locally: without a public HTTPS hostname Telegram cannot
reach a webhook. `BASE_URL` and `MINIAPP_URL` are still required — the app
refuses to start misconfigured rather than booting into a broken state.

```bash
# backend
cd backend
alembic upgrade head
python -m app.db.seed           # inserts the six groups, once
uvicorn app.main:app --reload

# frontend
cd miniapp
npm run dev                     # http://localhost:5173
```

The Mini App needs Telegram's `initData` to authenticate, so opening
`localhost:5173` directly shows "Илова Telegram орқали очилиши керак". Use a
tunnel and BotFather's Mini App URL to exercise it end to end.

## Layout

```
backend/
  app/
    main.py          FastAPI app, webhook route, lifespan
    config.py        settings; required values are required
    api/             auth (initData -> JWT), lessons, deps
    bot/handlers/    /start registration, voice note, confirm buttons
    services/        asr, llm, matcher, report, outbox worker
    db/              models, session (SQLite pragmas), queries, seed
  alembic/           migrations; `alembic check` is a CI gate
  tests/
miniapp/
  src/
    screens/         Today, Yesterday
    components/      StudentRow, DraftReview, VoiceStatus
    lib/             api (auth + refresh), sse, draft, telegram, types, date
docs/
```

## Things worth knowing before changing anything

- **`raw_note` and `note_private` never reach a student.** `services/report.py`
  reads six fields and neither of those is one of them, and a test asserts no
  API response contains them.
- **`summary_public` is AI-written and goes to the whole class.** `POST
  /confirm` returns 409 until the teacher has reviewed it.
- **Confirm is atomic and the outbox is unique per (lesson, student).** Both
  layers exist because either alone lets a double-tap send every report twice.
- **A student's `full_name` is attacker-chosen** — registration is open — and
  it goes into the prompt. It is validated at the door and the prompt marks it
  as data.
- **The Mini App persists unsaved work** (`lib/draft.ts`). A tab switch
  unmounts the screen, and Telegram closes on a swipe.

## Contributing

One commit per idea, conventional-commit prefix, and a body explaining *why*
when the reason is not obvious from the diff. CI must be green: backend lint +
migration check + tests with an 80% floor, frontend typecheck + lint + format +
tests + build, and a Docker image that starts and answers `/api/health`.

## Licence

All rights reserved. This is a private project for one teacher; there is no
licence granting use or redistribution.
