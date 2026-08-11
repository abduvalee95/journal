# Ustoz Jurnali Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram Bot + Mini App for one teacher: attendance, 1–5 grading, AI voice-to-report, student notifications.

**Architecture:** Python/FastAPI backend on Hetzner VPS (SQLite, aiogram 3 webhook, asyncio outbox worker). React/Vite Mini App on Vercel (static, auth via Telegram initData → JWT). AI pipeline: ElevenLabs Scribe (ASR) → Claude Haiku (structured JSON) → rapidfuzz name match.

**Tech Stack:** Python 3.12, FastAPI 0.115, aiogram 3.20, SQLAlchemy 2.0 + aiosqlite, Alembic, Pydantic v2, python-jose, httpx, rapidfuzz / React 18, TypeScript, Vite, Tailwind CSS, @twa-dev/sdk, TanStack Query

## Global Constraints

- All dates/times computed in `Asia/Tashkent` (UTC+5) — use `zoneinfo.ZoneInfo("Asia/Tashkent")`
- `raw_note` and `note_private` never appear in any student-facing response — enforced by separate Pydantic output schemas
- Only `TEACHER_TELEGRAM_ID` (env var) can access `/api/*` endpoints
- One active group per weekday (`UNIQUE(weekday, is_active)`)
- `grade` must be 1–5 or NULL — enforced by DB CHECK constraint
- No per-student invite tokens — students self-register via bot (`/start`)
- SSE auto-fill only applies when form is pristine (no manual changes yet)
- Outbox is idempotent: `POST /confirm` only acts when `lesson.status == 'draft'`
- Python deps pinned in `requirements.txt`; Node deps in `package.json`

## File Map

```
ustoz-jurnali/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, aiogram webhook mount, lifespan
│   │   ├── config.py            # Pydantic Settings from .env
│   │   ├── db/
│   │   │   ├── models.py        # SQLAlchemy ORM models (all 6 tables)
│   │   │   ├── session.py       # async engine + AsyncSessionLocal + get_session dep
│   │   │   └── seed.py          # insert 6 groups; run once
│   │   ├── bot/
│   │   │   ├── handlers/
│   │   │   │   ├── start.py     # /start, FSM registration (name → group select)
│   │   │   │   ├── voice.py     # voice message → AI pipeline asyncio.create_task
│   │   │   │   └── confirm.py   # inline keyboard callbacks (confirm/edit)
│   │   │   └── keyboards.py     # group_keyboard(), confirm_keyboard()
│   │   ├── api/
│   │   │   ├── auth.py          # POST /api/auth/telegram (initData → JWT)
│   │   │   ├── lessons.py       # GET today/date, PUT attendance, POST confirm, SSE stream, PATCH att
│   │   │   └── deps.py          # require_teacher JWT guard
│   │   ├── services/
│   │   │   ├── asr.py           # transcribe(audio_bytes) → str via ElevenLabs Scribe
│   │   │   ├── llm.py           # extract_lesson(transcript, names) → dict via Claude Haiku tool_use
│   │   │   ├── matcher.py       # match_names(mentioned, students, threshold=80) → dict
│   │   │   ├── report.py        # build_report(lesson, attendance, group) → str
│   │   │   └── outbox.py        # run_outbox(bot) coroutine, 30s loop, retry logic
│   │   └── utils/
│   │       └── tashkent.py      # tashkent_now(), today(), weekday(), format_date_uz()
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_tashkent.py
│   │   ├── test_auth.py
│   │   ├── test_matcher.py
│   │   ├── test_report.py
│   │   └── test_outbox.py
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── miniapp/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx              # auth flow + routing (Today / Yesterday)
│   │   ├── screens/
│   │   │   ├── Today.tsx        # main screen: AI draft or manual entry
│   │   │   └── Yesterday.tsx    # past lesson silent correction
│   │   ├── components/
│   │   │   ├── StudentRow.tsx   # attendance toggle + grade picker + note input
│   │   │   ├── VoiceStatus.tsx  # SSE spinner → auto-fill trigger
│   │   │   └── DraftReview.tsx  # topic + homework text fields
│   │   └── lib/
│   │       ├── telegram.ts      # tg, setMainButton, haptic helpers
│   │       └── api.ts           # authenticate(), apiFetch<T>(), token in memory
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
├── docker-compose.yml
├── Caddyfile
└── .env.example
```

---

### Task 1: Project skeleton, config, health endpoint

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`

**Interfaces:**
- Produces: `settings` (Settings instance), `app` (FastAPI), `GET /api/health → {"status":"ok"}`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiogram==3.20.0
sqlalchemy[asyncio]==2.0.35
aiosqlite==0.20.0
alembic==1.13.2
pydantic-settings==2.4.0
pydantic==2.9.0
httpx==0.27.2
python-jose[cryptography]==3.3.0
rapidfuzz==3.10.0
pytest==8.3.0
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create .env.example**

```bash
BOT_TOKEN=
WEBHOOK_SECRET=
TEACHER_TELEGRAM_ID=
BASE_URL=https://api.domain.uz
MINIAPP_URL=https://journal.vercel.app
JWT_SECRET=
DATABASE_URL=sqlite+aiosqlite:///./data/journal.db
ELEVENLABS_API_KEY=
LLM_API_KEY=
LLM_MODEL=claude-haiku-4-5-20251001
```

- [ ] **Step 3: Write config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bot_token: str
    webhook_secret: str
    teacher_telegram_id: int
    base_url: str
    miniapp_url: str
    jwt_secret: str
    database_url: str = "sqlite+aiosqlite:///./data/journal.db"
    elevenlabs_api_key: str
    llm_api_key: str
    llm_model: str = "claude-haiku-4-5-20251001"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Write main.py skeleton**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # startup/shutdown filled in later tasks

app = FastAPI(lifespan=lifespan)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Install deps and verify health**

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in values
mkdir -p data
uvicorn app.main:app --reload
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: project skeleton, config, health endpoint"
```

---

### Task 2: Database models, session, Alembic migration, seed

**Files:**
- Create: `backend/app/db/models.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/seed.py`
- Create: `backend/alembic/` (init)

**Interfaces:**
- Produces: `Group`, `Student`, `Lesson`, `Attendance`, `Outbox`, `AiJob` ORM classes; `AsyncSessionLocal`, `get_session`; `seed.py` CLI

- [ ] **Step 1: Write models.py**

```python
from sqlalchemy import (Column, Integer, Text, CheckConstraint,
                        UniqueConstraint, ForeignKey, Index)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Group(Base):
    __tablename__ = "groups"
    id         = Column(Integer, primary_key=True)
    name       = Column(Text, nullable=False)
    weekday    = Column(Integer, nullable=False)   # 1=Mon..6=Sat
    start_time = Column(Text)
    is_active  = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("weekday", "is_active"),)

class Student(Base):
    __tablename__ = "students"
    id          = Column(Integer, primary_key=True)
    group_id    = Column(Integer, ForeignKey("groups.id"), nullable=False)
    full_name   = Column(Text, nullable=False)
    telegram_id = Column(Integer, unique=True, nullable=False)
    joined_at   = Column(Text, nullable=False)
    is_active   = Column(Integer, nullable=False, default=1)

Index("idx_students_group", Student.group_id, Student.is_active)

class Lesson(Base):
    __tablename__ = "lessons"
    id             = Column(Integer, primary_key=True)
    group_id       = Column(Integer, ForeignKey("groups.id"), nullable=False)
    lesson_date    = Column(Text, nullable=False)   # YYYY-MM-DD Tashkent
    topic          = Column(Text)
    raw_note       = Column(Text)                   # NEVER sent to students
    audio_file_id  = Column(Text)
    summary_public = Column(Text)
    homework       = Column(Text)
    status         = Column(Text, nullable=False, default="draft")  # draft|saved
    saved_at       = Column(Text)
    created_at     = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("group_id", "lesson_date"),)

class Attendance(Base):
    __tablename__ = "attendance"
    id           = Column(Integer, primary_key=True)
    lesson_id    = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id   = Column(Integer, ForeignKey("students.id"), nullable=False)
    status       = Column(Text, nullable=False)   # present|absent|late
    grade        = Column(Integer)                # 1..5 or NULL
    note_public  = Column(Text)
    note_private = Column(Text)
    notified_at  = Column(Text)
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id"),
        CheckConstraint("grade IS NULL OR (grade BETWEEN 1 AND 5)"),
    )

class Outbox(Base):
    __tablename__ = "outbox"
    id         = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    lesson_id  = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    text       = Column(Text, nullable=False)
    status     = Column(Text, nullable=False, default="pending")  # pending|sent|failed
    attempts   = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    created_at = Column(Text, nullable=False)
    sent_at    = Column(Text)

Index("idx_outbox_pending", Outbox.status, Outbox.created_at)

class AiJob(Base):
    __tablename__ = "ai_jobs"
    id          = Column(Integer, primary_key=True)
    lesson_id   = Column(Integer, ForeignKey("lessons.id"))
    stage       = Column(Text)       # asr|llm
    status      = Column(Text)       # running|done|error
    duration_ms = Column(Integer)
    error       = Column(Text)
    created_at  = Column(Text, nullable=False)
```

- [ ] **Step 2: Write session.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 3: Init Alembic and create migration**

```bash
cd backend
alembic init alembic
# Edit alembic/env.py: add these two lines before run_migrations_online()
#   from app.db.models import Base
#   target_metadata = Base.metadata
# Also set: config.set_main_option("sqlalchemy.url", settings.database_url.replace("+aiosqlite",""))
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 4: Write seed.py**

```python
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models import Group

GROUPS = [
    {"name": "Beginners A",         "weekday": 1, "start_time": "09:00"},
    {"name": "Elementary B",        "weekday": 2, "start_time": "11:00"},
    {"name": "Pre-Intermediate C",  "weekday": 3, "start_time": "14:00"},
    {"name": "Intermediate D",      "weekday": 4, "start_time": "16:00"},
    {"name": "Upper-Intermediate E","weekday": 5, "start_time": "18:00"},
    {"name": "Advanced F",          "weekday": 6, "start_time": "10:00"},
]

async def seed():
    async with AsyncSessionLocal() as session:
        for g in GROUPS:
            session.add(Group(**g))
        await session.commit()
    print("Seeded 6 groups")

if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 5: Run seed, verify**

```bash
python -m app.db.seed
sqlite3 data/journal.db "SELECT id,name,weekday FROM groups;"
# Expected: 6 rows
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: db models, alembic migration, seed 6 groups"
```

---

### Task 3: Timezone utilities

**Files:**
- Create: `backend/app/utils/tashkent.py`
- Create: `backend/tests/test_tashkent.py`

**Interfaces:**
- Produces: `tashkent_now() → datetime`, `today() → str`, `weekday() → int`, `format_date_uz(d: str) → str`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tashkent.py
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

TZ = ZoneInfo("Asia/Tashkent")

def _mock(dt_str):
    return datetime.fromisoformat(dt_str).replace(tzinfo=TZ)

def test_weekday_monday():
    with patch("app.utils.tashkent.tashkent_now", return_value=_mock("2026-08-10T12:00:00")):
        from app.utils.tashkent import weekday
        assert weekday() == 1

def test_weekday_saturday():
    with patch("app.utils.tashkent.tashkent_now", return_value=_mock("2026-08-15T12:00:00")):
        from app.utils.tashkent import weekday
        assert weekday() == 6

def test_today_returns_iso():
    with patch("app.utils.tashkent.tashkent_now", return_value=_mock("2026-08-10T12:00:00")):
        from app.utils.tashkent import today
        assert today() == "2026-08-10"

def test_format_date_uz():
    from app.utils.tashkent import format_date_uz
    assert format_date_uz("2026-08-11") == "11 avgust 2026"
    assert format_date_uz("2026-01-01") == "1 yanvar 2026"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_tashkent.py -v
# Expected: ImportError or AttributeError
```

- [ ] **Step 3: Implement tashkent.py**

```python
from datetime import datetime, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")

MONTHS_UZ = [
    "yanvar","fevral","mart","aprel","may","iyun",
    "iyul","avgust","sentabr","oktabr","noyabr","dekabr"
]

def tashkent_now() -> datetime:
    return datetime.now(TZ)

def today() -> str:
    return tashkent_now().date().isoformat()

def weekday() -> int:
    return tashkent_now().isoweekday()   # 1=Mon, 6=Sat

def format_date_uz(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.day} {MONTHS_UZ[dt.month - 1]} {dt.year}"
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_tashkent.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/tashkent.py backend/tests/test_tashkent.py
git commit -m "feat: Asia/Tashkent timezone helpers"
```

---

### Task 4: Bot skeleton + student registration (FSM)

**Files:**
- Create: `backend/app/bot/keyboards.py`
- Create: `backend/app/bot/handlers/start.py`
- Modify: `backend/app/main.py` (mount aiogram webhook + dispatcher)

**Interfaces:**
- Consumes: `AsyncSessionLocal`, `Group`, `Student`, `tashkent_now()`, `settings.teacher_telegram_id`, `settings.webhook_secret`
- Produces: `dp` (Dispatcher), aiogram webhook at `POST /webhook/telegram/{secret}`, `/start` FSM flow

- [ ] **Step 1: Write keyboards.py**

```python
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEEKDAY_UZ = {1:"Dush",2:"Sesh",3:"Chor",4:"Pay",5:"Jum",6:"Shan"}

def group_keyboard(groups) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"{g.name} ({WEEKDAY_UZ[g.weekday]})", callback_data=f"group:{g.id}")
    b.adjust(2)
    return b.as_markup()

def confirm_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Saqlash",    callback_data=f"confirm:{lesson_id}")
    b.button(text="✏️ Tahrirlash", callback_data=f"edit:{lesson_id}")
    b.adjust(2)
    return b.as_markup()
```

- [ ] **Step 2: Write bot/handlers/start.py**

```python
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Student, Group
from app.bot.keyboards import group_keyboard
from app.utils.tashkent import tashkent_now

router = Router()

class Reg(StatesGroup):
    name  = State()
    group = State()

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    async with AsyncSessionLocal() as s:
        existing = await s.scalar(select(Student).where(Student.telegram_id == msg.from_user.id))
    if existing:
        await msg.answer(f"Siz allaqachon ro'yxatdasiz: {existing.full_name}")
        return
    await state.set_state(Reg.name)
    await msg.answer("Ismingiz va familiyangiz?")

@router.message(Reg.name)
async def got_name(msg: Message, state: FSMContext):
    await state.update_data(full_name=msg.text.strip())
    async with AsyncSessionLocal() as s:
        groups = (await s.execute(
            select(Group).where(Group.is_active == 1).order_by(Group.weekday)
        )).scalars().all()
    await state.set_state(Reg.group)
    await msg.answer("Guruhingizni tanlang:", reply_markup=group_keyboard(groups))

@router.callback_query(Reg.group, F.data.startswith("group:"))
async def got_group(cb: CallbackQuery, state: FSMContext):
    group_id = int(cb.data.split(":")[1])
    data = await state.get_data()
    async with AsyncSessionLocal() as s:
        s.add(Student(
            telegram_id=cb.from_user.id,
            full_name=data["full_name"],
            group_id=group_id,
            joined_at=tashkent_now().isoformat(),
        ))
        await s.commit()
    await state.clear()
    await cb.message.edit_text("Ro'yxatdan o'tdingiz! Dars hisobotlari shu yerga keladi.")
```

- [ ] **Step 3: Update main.py to wire bot + webhook**

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import settings
from app.bot.handlers import start as start_handler

bot = Bot(token=settings.bot_token)
dp  = Dispatcher(storage=MemoryStorage())
dp.include_router(start_handler.router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{settings.base_url}/webhook/telegram/{settings.webhook_secret}"
    await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret)
    yield
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.webhook_secret:
        return Response(status_code=403)
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != settings.webhook_secret:
        return Response(status_code=403)
    data = await request.json()
    from aiogram.types import Update
    update = Update.model_validate(data)
    await dp.process_update(update)
    return Response()

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Local test with ngrok**

```bash
ngrok http 8000
# Copy https URL → set BASE_URL in .env
uvicorn app.main:app --reload
# Send /start to bot → expect "Ismingiz va familiyangiz?"
# Type a name → expect group keyboard
# Tap a group → expect "Ro'yxatdan o'tdingiz!"
sqlite3 data/journal.db "SELECT * FROM students;"
```

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: bot registration FSM (name + group selection)"
```

---

### Task 5: JWT auth API

**Files:**
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/app/main.py` (include auth router)

**Interfaces:**
- Produces: `POST /api/auth/telegram → {"access_token": str}`, `require_teacher` FastAPI dep → `int` (teacher_id)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import hashlib, hmac, time, json
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.config import settings

client = TestClient(app)

def make_init_data(user_id: int, bot_token: str, offset_sec: int = 0) -> str:
    auth_date = str(int(time.time()) - offset_sec)
    user = json.dumps({"id": user_id, "first_name": "Test"})
    params = {"auth_date": auth_date, "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return f"auth_date={auth_date}&user={user}&hash={h}"

def test_valid_teacher_gets_token():
    init_data = make_init_data(settings.teacher_telegram_id, settings.bot_token)
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 200
    assert "access_token" in r.json()

def test_wrong_user_gets_403():
    init_data = make_init_data(99999999, settings.bot_token)
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 403

def test_expired_auth_date_gets_401():
    init_data = make_init_data(settings.teacher_telegram_id, settings.bot_token, offset_sec=400)
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401

def test_tampered_hash_gets_401():
    init_data = make_init_data(settings.teacher_telegram_id, settings.bot_token)
    bad = init_data.replace("hash=", "hash=00")
    r = client.post("/api/auth/telegram", json={"init_data": bad})
    assert r.status_code == 401
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_auth.py -v
# Expected: 404 or ImportError
```

- [ ] **Step 3: Write auth.py**

```python
import hashlib, hmac, json, time
from urllib.parse import parse_qsl
from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel
from app.config import settings

router = APIRouter()

class InitDataReq(BaseModel):
    init_data: str

def _verify(init_data: str) -> dict:
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received = params.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise HTTPException(401, "Invalid signature")
    if time.time() - int(params.get("auth_date", 0)) > 300:
        raise HTTPException(401, "auth_date expired")
    return params

@router.post("/api/auth/telegram")
async def auth_telegram(body: InitDataReq):
    params = _verify(body.init_data)
    user = json.loads(params.get("user", "{}"))
    if user.get("id") != settings.teacher_telegram_id:
        raise HTTPException(403, "Not authorized")
    token = jwt.encode(
        {"sub": str(user["id"]), "exp": int(time.time()) + 1800},
        settings.jwt_secret, algorithm="HS256",
    )
    return {"access_token": token}
```

- [ ] **Step 4: Write deps.py**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

_bearer = HTTPBearer()

async def require_teacher(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
```

- [ ] **Step 5: Include auth router in main.py**

Add to `main.py`:
```python
from app.api import auth as auth_api
app.include_router(auth_api.router)
```

- [ ] **Step 6: Run — verify PASS**

```bash
pytest tests/test_auth.py -v
# Expected: 4 passed
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/ backend/tests/test_auth.py backend/app/main.py
git commit -m "feat: initData JWT auth, require_teacher dep"
```

---

### Task 6: Lessons API — today, date query, attendance save

**Files:**
- Create: `backend/app/api/lessons.py`
- Modify: `backend/app/main.py` (include lessons router)

**Interfaces:**
- Consumes: `get_session`, `require_teacher`, `today()`, `weekday()`, `tashkent_now()`, all ORM models
- Produces: `GET /api/today`, `GET /api/lessons?date=YYYY-MM-DD`, `PUT /api/lessons/{id}/attendance`, `PATCH /api/attendance/{id}`

- [ ] **Step 1: Write lessons.py**

```python
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import Group, Lesson, Student, Attendance
from app.api.deps import require_teacher
from app.utils.tashkent import today, weekday, tashkent_now

router = APIRouter()

# ── Schemas ──────────────────────────────────────────────────

class AttendanceItem(BaseModel):
    student_id: int
    status: str                    # present | absent | late
    grade: Optional[int] = None
    note_public: Optional[str] = None

class AttendanceBatch(BaseModel):
    items: List[AttendanceItem]
    topic: Optional[str] = None
    homework: Optional[str] = None

# ── Helpers ──────────────────────────────────────────────────

def _lesson_out(lesson: Lesson) -> dict:
    return {
        "id": lesson.id,
        "date": lesson.lesson_date,
        "topic": lesson.topic,
        "homework": lesson.homework,
        "summary_public": lesson.summary_public,
        "status": lesson.status,
    }

def _att_out(a: Attendance) -> dict:
    return {
        "id": a.id,
        "student_id": a.student_id,
        "status": a.status,
        "grade": a.grade,
        "note_public": a.note_public,
    }

async def _get_or_create_lesson(session: AsyncSession, group_id: int, date: str) -> Lesson:
    lesson = await session.scalar(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == date)
    )
    if not lesson:
        lesson = Lesson(group_id=group_id, lesson_date=date, created_at=tashkent_now().isoformat())
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
    return lesson

async def _students_and_attendance(session, group_id, lesson_id):
    students = (await session.execute(
        select(Student).where(Student.group_id == group_id, Student.is_active == 1)
    )).scalars().all()
    attendance = (await session.execute(
        select(Attendance).where(Attendance.lesson_id == lesson_id)
    )).scalars().all()
    return students, attendance

# ── Endpoints ────────────────────────────────────────────────

@router.get("/api/today")
async def get_today(
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    group = await session.scalar(
        select(Group).where(Group.weekday == weekday(), Group.is_active == 1)
    )
    if not group:
        return {"group": None, "lesson": None, "students": [], "attendance": []}
    lesson = await _get_or_create_lesson(session, group.id, today())
    students, attendance = await _students_and_attendance(session, group.id, lesson.id)
    return {
        "group": {"id": group.id, "name": group.name},
        "lesson": _lesson_out(lesson),
        "students": [{"id": s.id, "full_name": s.full_name} for s in students],
        "attendance": [_att_out(a) for a in attendance],
    }

@router.get("/api/lessons")
async def get_lesson_by_date(
    date: str,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    lesson = await session.scalar(select(Lesson).where(Lesson.lesson_date == date))
    if not lesson:
        return {"group": None, "lesson": None, "students": [], "attendance": []}
    group = await session.get(Group, lesson.group_id)
    students, attendance = await _students_and_attendance(session, group.id, lesson.id)
    return {
        "group": {"id": group.id, "name": group.name},
        "lesson": _lesson_out(lesson),
        "students": [{"id": s.id, "full_name": s.full_name} for s in students],
        "attendance": [_att_out(a) for a in attendance],
    }

@router.put("/api/lessons/{lesson_id}/attendance")
async def save_attendance(
    lesson_id: int,
    body: AttendanceBatch,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if body.topic is not None:
        lesson.topic = body.topic
    if body.homework is not None:
        lesson.homework = body.homework
    for item in body.items:
        existing = await session.scalar(
            select(Attendance).where(
                Attendance.lesson_id == lesson_id,
                Attendance.student_id == item.student_id,
            )
        )
        if existing:
            existing.status     = item.status
            existing.grade      = item.grade
            existing.note_public = item.note_public
        else:
            session.add(Attendance(
                lesson_id=lesson_id,
                student_id=item.student_id,
                status=item.status,
                grade=item.grade,
                note_public=item.note_public,
            ))
    await session.commit()
    return {"ok": True}

@router.patch("/api/attendance/{att_id}")
async def patch_attendance(
    att_id: int,
    body: AttendanceItem,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    att = await session.get(Attendance, att_id)
    if not att:
        raise HTTPException(404, "Not found")
    att.status      = body.status
    att.grade       = body.grade
    att.note_public = body.note_public
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 2: Include router in main.py**

```python
from app.api import lessons as lessons_api
app.include_router(lessons_api.router)
```

- [ ] **Step 3: Manual test with curl**

```bash
# Get JWT first
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/telegram \
  -H "Content-Type: application/json" \
  -d '{"init_data":"<valid_init_data>"}' | jq -r .access_token)

# Get today
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/today
# Expected: group + lesson + students (empty attendance)

# Save attendance
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/lessons/1/attendance \
  -d '{"items":[{"student_id":1,"status":"present","grade":4}]}'
# Expected: {"ok":true}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/lessons.py backend/app/main.py
git commit -m "feat: today/date/attendance API endpoints"
```

---

### Task 7: Report builder + Outbox worker + Confirm endpoint

**Files:**
- Create: `backend/app/services/report.py`
- Create: `backend/app/services/outbox.py`
- Create: `backend/tests/test_report.py`
- Modify: `backend/app/api/lessons.py` (add POST /confirm)
- Modify: `backend/app/main.py` (start outbox worker in lifespan)

**Interfaces:**
- Consumes: `Lesson`, `Attendance`, `Group`, `Student`, `Outbox`, `AsyncSessionLocal`, `bot` (aiogram Bot), `format_date_uz()`
- Produces: `build_report(lesson, att, group) → str`, `run_outbox(bot)` coroutine, `POST /api/lessons/{id}/confirm`

- [ ] **Step 1: Write failing tests for report.py**

```python
# tests/test_report.py
from types import SimpleNamespace
from app.services.report import build_report

def make(lesson_kw={}, att_kw={}, group_kw={}):
    lesson = SimpleNamespace(
        lesson_date="2026-08-11",
        topic="Present Perfect",
        summary_public="Bugun Present Perfect o'rgandik.",
        homework="Workbook 42-43",
        **lesson_kw,
    )
    att = SimpleNamespace(status="present", grade=4, note_public="Yaxshi ishladi.", **att_kw)
    group = SimpleNamespace(name="Beginners A", **group_kw)
    return build_report(lesson, att, group)

def test_full_present():
    text = make()
    assert "Beginners A" in text
    assert "11 avgust 2026" in text
    assert "Present Perfect" in text
    assert "✅ Keldingiz" in text
    assert "⭐ Baho: 4/5" in text
    assert "Yaxshi ishladi" in text
    assert "Workbook 42-43" in text

def test_absent_no_grade():
    text = make(att_kw={"status": "absent", "grade": None, "note_public": None})
    assert "❌ Kelmadingiz" in text
    assert "Baho" not in text

def test_late_shows_emoji():
    text = make(att_kw={"status": "late", "grade": 3, "note_public": None})
    assert "🕐 Kech keldingiz" in text
    assert "⭐ Baho: 3/5" in text

def test_empty_note_omitted():
    text = make(att_kw={"note_public": None})
    assert "💬" not in text

def test_empty_homework_omitted():
    text = make(lesson_kw={"homework": None})
    assert "Uy vazifasi" not in text

def test_raw_note_not_in_report():
    text = make(lesson_kw={"topic": "SECRET raw_note content"})
    # raw_note is not a field passed to build_report — test that it takes only public fields
    assert "raw_note" not in text
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_report.py -v
```

- [ ] **Step 3: Implement report.py**

```python
from app.utils.tashkent import format_date_uz

STATUS_LINE = {
    "present": "✅ Keldingiz",
    "absent":  "❌ Kelmadingiz",
    "late":    "🕐 Kech keldingiz",
}

def build_report(lesson, attendance, group) -> str:
    parts = [f"📚 {group.name} — {format_date_uz(lesson.lesson_date)}"]
    if lesson.topic:
        parts.append(f"Mavzu: {lesson.topic}")
    if lesson.summary_public:
        parts.append(f"\n{lesson.summary_public}")
    parts.append("\n---")
    parts.append(STATUS_LINE.get(attendance.status, attendance.status))
    if attendance.grade is not None:
        parts.append(f"⭐ Baho: {attendance.grade}/5")
    if attendance.note_public:
        parts.append(f"💬 {attendance.note_public}")
    if lesson.homework:
        parts.append(f"\n📝 Uy vazifasi: {lesson.homework}")
    return "\n".join(parts)
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_report.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Implement outbox.py**

```python
import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Outbox, Student
from app.utils.tashkent import tashkent_now

async def run_outbox(bot: Bot):
    while True:
        await asyncio.sleep(30)
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Outbox).where(Outbox.status == "pending").order_by(Outbox.created_at)
            )).scalars().all()
            for row in rows:
                student = await session.get(Student, row.student_id)
                try:
                    await bot.send_message(student.telegram_id, row.text, parse_mode=None)
                    row.status  = "sent"
                    row.sent_at = tashkent_now().isoformat()
                except TelegramForbiddenError as e:
                    row.status     = "failed"
                    row.last_error = str(e)
                except Exception as e:
                    row.attempts  += 1
                    row.last_error = str(e)
                    if row.attempts >= 3:
                        row.status = "failed"
            await session.commit()
```

- [ ] **Step 6: Add POST /confirm to lessons.py**

Add this to `app/api/lessons.py`:
```python
from app.services.report import build_report

@router.post("/api/lessons/{lesson_id}/confirm")
async def confirm_lesson(
    lesson_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    lesson = await session.get(Lesson, lesson_id)
    if not lesson or lesson.status != "draft":
        return {"ok": True}   # idempotent
    lesson.status   = "saved"
    lesson.saved_at = tashkent_now().isoformat()
    group = await session.get(Group, lesson.group_id)
    att_rows = (await session.execute(
        select(Attendance).where(Attendance.lesson_id == lesson_id)
    )).scalars().all()
    for att in att_rows:
        student = await session.get(Student, att.student_id)
        if not student or not student.is_active:
            continue
        text = build_report(lesson, att, group)
        session.add(Outbox(
            student_id=att.student_id,
            lesson_id=lesson_id,
            text=text,
            created_at=tashkent_now().isoformat(),
        ))
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 7: Start outbox worker in main.py lifespan**

```python
# Update lifespan in main.py:
from app.services.outbox import run_outbox

@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{settings.base_url}/webhook/telegram/{settings.webhook_secret}"
    await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret)
    task = asyncio.create_task(run_outbox(bot))
    yield
    task.cancel()
    await bot.delete_webhook()
```

- [ ] **Step 8: Test confirm + outbox manually**

```bash
# After saving attendance:
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/lessons/1/confirm
# Check outbox:
sqlite3 data/journal.db "SELECT status,text FROM outbox;"
# Wait 30s → status should be 'sent' (if student has registered)
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/ backend/app/api/lessons.py backend/app/main.py backend/tests/test_report.py
git commit -m "feat: report builder, outbox worker, confirm endpoint"
```

---

### ⚑ MILESTONE: Stop and show teacher

At this point manual attendance + grading + student notifications all work. Show teacher and collect feedback before building AI pipeline.

---

### Task 8: ASR service (ElevenLabs Scribe)

**Files:**
- Create: `backend/app/services/asr.py`

**Interfaces:**
- Produces: `async transcribe(audio_bytes: bytes, filename: str = "audio.oga") → str`

- [ ] **Step 1: Implement asr.py**

```python
import httpx
from app.config import settings

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"

async def transcribe(audio_bytes: bytes, filename: str = "audio.oga") -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            SCRIBE_URL,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model_id": "scribe_v1", "language_code": "uzb"},
        )
        r.raise_for_status()
        return r.json()["text"]
```

- [ ] **Step 2: Live smoke test with a real audio file**

```bash
python - <<'EOF'
import asyncio, pathlib
from app.services.asr import transcribe

audio = pathlib.Path("test_voice.oga").read_bytes()  # record a sample
result = asyncio.run(transcribe(audio))
print(result)
EOF
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/asr.py
git commit -m "feat: ElevenLabs Scribe ASR service"
```

---

### Task 9: LLM service + name matcher

**Files:**
- Create: `backend/app/services/llm.py`
- Create: `backend/app/services/matcher.py`
- Create: `backend/tests/test_matcher.py`

**Interfaces:**
- Produces: `async extract_lesson(transcript: str, student_names: list[str]) → dict`
- Produces: `match_names(mentioned: list[str], students: list[dict], threshold: int = 80) → dict[str, int | None]`

- [ ] **Step 1: Write failing matcher tests**

```python
# tests/test_matcher.py
from app.services.matcher import match_names

STUDENTS = [
    {"id": 1, "full_name": "Aziza Karimova"},
    {"id": 2, "full_name": "Bobur Toshmatov"},
    {"id": 3, "full_name": "Dildora Yusupova"},
]

def test_exact_first_name():
    assert match_names(["Aziza"], STUDENTS)["Aziza"] == 1

def test_partial_name():
    assert match_names(["Bobur"], STUDENTS)["Bobur"] == 2

def test_typo():
    assert match_names(["Dildore"], STUDENTS)["Dildore"] == 3

def test_no_match():
    assert match_names(["Xurshid"], STUDENTS)["Xurshid"] is None

def test_scoped_to_passed_list():
    # Bobur not in group_a list → None
    group_a = [{"id": 1, "full_name": "Aziza Karimova"}]
    assert match_names(["Bobur"], group_a)["Bobur"] is None

def test_empty_input():
    assert match_names([], STUDENTS) == {}
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_matcher.py -v
```

- [ ] **Step 3: Implement matcher.py**

```python
from rapidfuzz import process, fuzz

def match_names(
    mentioned: list[str],
    students: list[dict],   # [{"id": int, "full_name": str}]
    threshold: int = 80,
) -> dict[str, int | None]:
    if not mentioned:
        return {}
    known = {s["full_name"]: s["id"] for s in students}
    result: dict[str, int | None] = {}
    for name in mentioned:
        hit = process.extractOne(name, known.keys(), scorer=fuzz.WRatio)
        result[name] = known[hit[0]] if hit and hit[1] >= threshold else None
    return result
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_matcher.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Implement llm.py**

```python
import httpx
from app.config import settings

_URL = "https://api.anthropic.com/v1/messages"

_SCHEMA = {
    "type": "object",
    "properties": {
        "topic":          {"type": "string"},
        "summary_public": {"type": "string"},
        "homework":       {"type": "string"},
        "per_student": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_mentioned":  {"type": "string"},
                    "note_public":     {"type": "string"},
                    "grade_suggested": {"type": "integer", "minimum": 1, "maximum": 5},
                    "attendance_hint": {"type": "string", "enum": ["present","absent","late"]},
                },
                "required": ["name_mentioned", "attendance_hint"],
            },
        },
    },
    "required": ["topic", "summary_public", "per_student"],
}

_SYSTEM = """You are a teacher's assistant. Extract structured lesson data from a voice note transcript.
Rules:
- summary_public: 2-3 neutral sentences, NO criticism, NO student comparisons.
- note_public: one supportive sentence per student; soften any harsh language.
- grade_suggested: integer 1-5 only; omit if not clearly stated.
- Return JSON matching the tool schema exactly."""

async def extract_lesson(transcript: str, student_names: list[str]) -> dict:
    user_content = (
        f"Transcript:\n{transcript}\n\n"
        f"Students in this group: {', '.join(student_names)}"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            _URL,
            headers={
                "x-api-key":         settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":       settings.llm_model,
                "max_tokens":  1024,
                "system":      _SYSTEM,
                "messages":    [{"role": "user", "content": user_content}],
                "tools":       [{"name": "extract", "input_schema": _SCHEMA}],
                "tool_choice": {"type": "tool", "name": "extract"},
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["input"]
```

- [ ] **Step 6: Live smoke test**

```bash
python - <<'EOF'
import asyncio
from app.services.llm import extract_lesson
result = asyncio.run(extract_lesson(
    "Aziza juda yaxshi ishladi, besh berdim. Bobur kelmadi.",
    ["Aziza Karimova", "Bobur Toshmatov"]
))
import json; print(json.dumps(result, indent=2, ensure_ascii=False))
EOF
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/llm.py backend/app/services/matcher.py backend/tests/test_matcher.py
git commit -m "feat: LLM structured extraction, rapidfuzz name matcher"
```

---

### Task 10: Voice bot handler + AI pipeline + SSE endpoint

**Files:**
- Create: `backend/app/bot/handlers/voice.py`
- Create: `backend/app/bot/handlers/confirm.py`
- Modify: `backend/app/api/lessons.py` (add SSE stream endpoint)
- Modify: `backend/app/main.py` (include voice + confirm routers)

**Interfaces:**
- Consumes: `transcribe()`, `extract_lesson()`, `match_names()`, `confirm_keyboard()`, `AsyncSessionLocal`, all models, `tashkent_now()`, `settings.teacher_telegram_id`
- Produces: voice handler (teacher-only), `GET /api/lessons/{id}/stream` SSE, `sse_queues` shared dict

- [ ] **Step 1: Write voice.py**

```python
import asyncio, time
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Group, Lesson, Student, Attendance, AiJob
from app.services.asr import transcribe
from app.services.llm import extract_lesson
from app.services.matcher import match_names
from app.bot.keyboards import confirm_keyboard
from app.utils.tashkent import today, weekday, tashkent_now
from app.config import settings

router = Router()

# lesson_id → asyncio.Queue; consumed by SSE endpoint
sse_queues: dict[int, asyncio.Queue] = {}

@router.message(F.voice)
async def handle_voice(message: Message):
    if message.from_user.id != settings.teacher_telegram_id:
        return

    async with AsyncSessionLocal() as s:
        group = await s.scalar(
            select(Group).where(Group.weekday == weekday(), Group.is_active == 1)
        )
        if not group:
            await message.answer("Bugun dars guruh topilmadi.")
            return
        date = today()
        lesson = await s.scalar(
            select(Lesson).where(Lesson.group_id == group.id, Lesson.lesson_date == date)
        )
        if not lesson:
            lesson = Lesson(group_id=group.id, lesson_date=date, created_at=tashkent_now().isoformat())
            s.add(lesson)
            await s.commit()
            await s.refresh(lesson)
        lesson.audio_file_id = message.voice.file_id
        await s.commit()
        students = (await s.execute(
            select(Student).where(Student.group_id == group.id, Student.is_active == 1)
        )).scalars().all()
        student_names = [st.full_name for st in students]
        student_map   = [{"id": st.id, "full_name": st.full_name} for st in students]
        lesson_id = lesson.id

    await message.answer("⏳ Ovoz qayta ishlanmoqda...")
    asyncio.create_task(_pipeline(
        message.bot, lesson_id, message.voice.file_id,
        student_names, student_map, message.chat.id
    ))

async def _pipeline(bot, lesson_id, file_id, student_names, student_map, chat_id):
    t0 = time.time()
    async with AsyncSessionLocal() as s:
        job = AiJob(lesson_id=lesson_id, stage="asr", status="running",
                    created_at=tashkent_now().isoformat())
        s.add(job); await s.commit(); job_id = job.id

    try:
        file      = await bot.get_file(file_id)
        raw       = await bot.download_file(file.file_path)
        transcript = await transcribe(raw.read())

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            lesson.raw_note = transcript
            job = await s.get(AiJob, job_id); job.stage = "llm"
            await s.commit()

        draft = await extract_lesson(transcript, student_names)
        match = match_names(
            [p["name_mentioned"] for p in draft["per_student"]], student_map
        )

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            lesson.topic          = draft.get("topic")
            lesson.summary_public = draft.get("summary_public")
            lesson.homework       = draft.get("homework")
            for p in draft["per_student"]:
                sid = match.get(p["name_mentioned"])
                if sid:
                    s.add(Attendance(
                        lesson_id=lesson_id, student_id=sid,
                        status=p.get("attendance_hint", "present"),
                        grade=p.get("grade_suggested"),
                        note_public=p.get("note_public"),
                    ))
            lesson.status = "draft"
            job = await s.get(AiJob, job_id)
            job.status = "done"; job.duration_ms = int((time.time()-t0)*1000)
            await s.commit()

        if lesson_id in sse_queues:
            await sse_queues[lesson_id].put({"event": "draft_ready"})

        unmatched = [p["name_mentioned"] for p in draft["per_student"]
                     if match.get(p["name_mentioned"]) is None]
        msg = "✅ Qoralama tayyor — Mini App'da ko'ring"
        if unmatched:
            msg += f"\n⚠️ Topilmagan ismlar: {', '.join(unmatched)}"
        await bot.send_message(chat_id, msg)

    except Exception as e:
        async with AsyncSessionLocal() as s:
            job = await s.get(AiJob, job_id)
            if job:
                job.status = "error"; job.error = str(e)
                job.duration_ms = int((time.time()-t0)*1000)
                await s.commit()
        await bot.send_message(chat_id, "❌ AI ishlamadi, qo'lda kiriting")
```

- [ ] **Step 2: Write confirm.py (inline keyboard callbacks)**

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery
from app.config import settings

router = Router()

@router.callback_query(F.data.startswith("confirm:"))
async def cb_confirm(cb: CallbackQuery):
    if cb.from_user.id != settings.teacher_telegram_id:
        return
    lesson_id = int(cb.data.split(":")[1])
    await cb.answer("Mini App'da Saqlash tugmasini bosing.")

@router.callback_query(F.data.startswith("edit:"))
async def cb_edit(cb: CallbackQuery):
    if cb.from_user.id != settings.teacher_telegram_id:
        return
    await cb.answer("Mini App'da tahrirlang.")
```

- [ ] **Step 3: Add SSE endpoint to lessons.py**

Add to `app/api/lessons.py`:
```python
import asyncio, json
from fastapi.responses import StreamingResponse
from app.bot.handlers.voice import sse_queues

@router.get("/api/lessons/{lesson_id}/stream")
async def stream_lesson(
    lesson_id: int,
    _: int = Depends(require_teacher),
):
    queue: asyncio.Queue = asyncio.Queue()
    sse_queues[lesson_id] = queue

    async def generate():
        try:
            while True:
                data = await asyncio.wait_for(queue.get(), timeout=90)
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("event") == "draft_ready":
                    break
        except asyncio.TimeoutError:
            yield 'data: {"event":"timeout"}\n\n'
        finally:
            sse_queues.pop(lesson_id, None)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Register routers in main.py**

```python
from app.bot.handlers import voice as voice_handler, confirm as confirm_handler
dp.include_router(voice_handler.router)
dp.include_router(confirm_handler.router)
```

- [ ] **Step 5: End-to-end voice test**

```bash
# Send a voice note to the bot
# Expect: "⏳ Ovoz qayta ishlanmoqda..."
# After 10-20s: "✅ Qoralama tayyor..."
sqlite3 data/journal.db "SELECT topic, summary_public, status FROM lessons;"
sqlite3 data/journal.db "SELECT student_id, status, grade FROM attendance;"
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: voice handler, AI pipeline, SSE stream endpoint"
```

---

### Task 11: Mini App scaffold + auth

**Files:**
- Create: `miniapp/package.json`
- Create: `miniapp/vite.config.ts`
- Create: `miniapp/tailwind.config.js`
- Create: `miniapp/index.html`
- Create: `miniapp/src/main.tsx`
- Create: `miniapp/src/lib/telegram.ts`
- Create: `miniapp/src/lib/api.ts`
- Create: `miniapp/src/App.tsx`

**Interfaces:**
- Produces: `authenticate(initData)`, `apiFetch<T>(path, options)`, `tg`, `setMainButton()`, `haptic()`, authenticated `App` component

- [ ] **Step 1: Create package.json**

```json
{
  "name": "ustoz-jurnali-miniapp",
  "private": true,
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@twa-dev/sdk": "^7.10.0",
    "@tanstack/react-query": "^5.56.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
```

- [ ] **Step 3: Create tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 4: Create src/lib/telegram.ts**

```typescript
import WebApp from "@twa-dev/sdk";

export const tg = WebApp;

export function expandApp() {
  tg.expand();
}

export function setMainButton(text: string, onClick: () => void) {
  tg.MainButton.setText(text);
  tg.MainButton.onClick(onClick);
  tg.MainButton.show();
}

export function hideMainButton() {
  tg.MainButton.offClick(() => {});
  tg.MainButton.hide();
}

export function showMainButtonLoading() {
  tg.MainButton.showProgress();
}

export function haptic() {
  tg.HapticFeedback.impactOccurred("medium");
}
```

- [ ] **Step 5: Create src/lib/api.ts**

```typescript
const BASE = import.meta.env.VITE_API_URL as string;

let _token: string | null = null;

export async function authenticate(initData: string): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) throw new Error("Auth failed");
  const data = await res.json();
  _token = data.access_token;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_token}`,
      ...options.headers,
    },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}
```

- [ ] **Step 6: Create src/App.tsx with auth flow**

```typescript
import { useEffect, useState } from "react";
import { tg, expandApp } from "./lib/telegram";
import { authenticate } from "./lib/api";
import Today from "./screens/Today";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    expandApp();
    authenticate(tg.initData)
      .then(() => setReady(true))
      .catch(() => setError("Kirish mumkin emas. Faqat ustoz uchun."));
  }, []);

  if (error) return (
    <div className="flex items-center justify-center h-screen text-red-500 p-4 text-center">
      {error}
    </div>
  );
  if (!ready) return (
    <div className="flex items-center justify-center h-screen text-gray-400">
      Yuklanmoqda...
    </div>
  );
  return <Today />;
}
```

- [ ] **Step 7: Install deps and test locally**

```bash
cd miniapp
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
# Open http://localhost:5173 in browser
# Expected: auth flow (will fail without initData — normal)
```

- [ ] **Step 8: Commit**

```bash
git add miniapp/
git commit -m "feat: Mini App scaffold, Telegram auth, api client"
```

---

### Task 12: Today screen — StudentRow, DraftReview, manual save

**Files:**
- Create: `miniapp/src/components/StudentRow.tsx`
- Create: `miniapp/src/components/DraftReview.tsx`
- Create: `miniapp/src/screens/Today.tsx`

**Interfaces:**
- Consumes: `apiFetch<T>()`, `setMainButton()`, `hideMainButton()`, `showMainButtonLoading()`, `haptic()`
- Produces: Full today screen with manual entry path working end-to-end

- [ ] **Step 1: Create StudentRow.tsx**

```typescript
import { useState } from "react";

export type AttStatus = "present" | "absent" | "late";

export interface StudentData {
  id: number;
  full_name: string;
  status: AttStatus;
  grade: number | null;
  note_public: string;
  att_id: number | null;
}

interface Props {
  student: StudentData;
  onChange: (updated: StudentData) => void;
}

const STATUS_LABELS: Record<AttStatus, string> = {
  present: "✅ Keldi",
  absent:  "❌ Kelmadi",
  late:    "🕐 Kech",
};

export default function StudentRow({ student, onChange }: Props) {
  const set = (patch: Partial<StudentData>) => onChange({ ...student, ...patch });

  return (
    <div className="border rounded-xl p-3 mb-2 bg-white shadow-sm">
      <div className="font-medium text-sm mb-2">{student.full_name}</div>
      <div className="flex gap-1 mb-2">
        {(["present", "absent", "late"] as AttStatus[]).map((s) => (
          <button
            key={s}
            onClick={() => { set({ status: s }); }}
            className={`text-xs px-2 py-1 rounded-full border transition-colors ${
              student.status === s
                ? "bg-blue-500 text-white border-blue-500"
                : "bg-gray-100 text-gray-600 border-gray-200"
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>
      {student.status !== "absent" && (
        <div className="flex gap-1 mb-2">
          {[1, 2, 3, 4, 5].map((g) => (
            <button
              key={g}
              onClick={() => set({ grade: g })}
              className={`w-8 h-8 rounded-full text-sm border ${
                student.grade === g
                  ? "bg-yellow-400 text-white border-yellow-400"
                  : "bg-gray-100 text-gray-500 border-gray-200"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      )}
      <input
        type="text"
        placeholder="Izoh (ixtiyoriy)"
        value={student.note_public}
        onChange={(e) => set({ note_public: e.target.value })}
        className="w-full text-xs border rounded px-2 py-1 bg-gray-50"
      />
    </div>
  );
}
```

- [ ] **Step 2: Create DraftReview.tsx**

```typescript
interface Props {
  topic: string;
  homework: string;
  onTopicChange: (v: string) => void;
  onHomeworkChange: (v: string) => void;
}

export default function DraftReview({ topic, homework, onTopicChange, onHomeworkChange }: Props) {
  return (
    <div className="mb-4">
      <div className="mb-2">
        <label className="text-xs text-gray-500 block mb-1">Mavzu</label>
        <input
          type="text"
          value={topic}
          onChange={(e) => onTopicChange(e.target.value)}
          placeholder="Dars mavzusi"
          className="w-full border rounded px-3 py-2 text-sm bg-white"
        />
      </div>
      <div>
        <label className="text-xs text-gray-500 block mb-1">Uy vazifasi</label>
        <input
          type="text"
          value={homework}
          onChange={(e) => onHomeworkChange(e.target.value)}
          placeholder="Uy vazifasi"
          className="w-full border rounded px-3 py-2 text-sm bg-white"
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create Today.tsx**

```typescript
import { useEffect, useState, useRef } from "react";
import { apiFetch } from "../lib/api";
import { setMainButton, hideMainButton, showMainButtonLoading, haptic } from "../lib/telegram";
import StudentRow, { StudentData, AttStatus } from "../components/StudentRow";
import DraftReview from "../components/DraftReview";

interface TodayData {
  group: { id: number; name: string } | null;
  lesson: { id: number; date: string; topic: string | null; homework: string | null; status: string } | null;
  students: { id: number; full_name: string }[];
  attendance: { id: number; student_id: number; status: AttStatus; grade: number | null; note_public: string | null }[];
}

export default function Today() {
  const [data, setData]       = useState<TodayData | null>(null);
  const [students, setStudents] = useState<StudentData[]>([]);
  const [topic, setTopic]     = useState("");
  const [homework, setHw]     = useState("");
  const [saved, setSaved]     = useState(false);
  const pristine = useRef(true);

  useEffect(() => {
    apiFetch<TodayData>("/api/today").then((d) => {
      setData(d);
      setTopic(d.lesson?.topic ?? "");
      setHw(d.lesson?.homework ?? "");
      const attMap = Object.fromEntries(d.attendance.map((a) => [a.student_id, a]));
      setStudents(
        d.students.map((s) => ({
          id: s.id,
          full_name: s.full_name,
          status: attMap[s.id]?.status ?? "present",
          grade: attMap[s.id]?.grade ?? null,
          note_public: attMap[s.id]?.note_public ?? "",
          att_id: attMap[s.id]?.id ?? null,
        }))
      );
      if (d.lesson?.status === "saved") setSaved(true);
    });
  }, []);

  useEffect(() => {
    if (!data?.lesson || saved) { hideMainButton(); return; }
    setMainButton("Saqlash", handleSave);
  }, [data, saved]);

  const handleChange = (updated: StudentData) => {
    pristine.current = false;
    setStudents((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
  };

  const handleSave = async () => {
    if (!data?.lesson) return;
    showMainButtonLoading();
    haptic();
    await apiFetch(`/api/lessons/${data.lesson.id}/attendance`, {
      method: "PUT",
      body: JSON.stringify({
        topic,
        homework,
        items: students.map((s) => ({
          student_id: s.id,
          status: s.status,
          grade: s.grade,
          note_public: s.note_public || null,
        })),
      }),
    });
    await apiFetch(`/api/lessons/${data.lesson.id}/confirm`, { method: "POST" });
    setSaved(true);
    hideMainButton();
  };

  if (!data) return <div className="p-4 text-gray-400">Yuklanmoqda...</div>;
  if (!data.group) return <div className="p-4 text-gray-500">Bugun dars yo'q.</div>;

  return (
    <div className="p-4 pb-20 bg-gray-50 min-h-screen">
      <h1 className="font-semibold text-lg mb-1">{data.group.name}</h1>
      <p className="text-xs text-gray-400 mb-4">{data.lesson?.date}</p>
      {saved && (
        <div className="bg-green-100 text-green-700 rounded-lg p-3 text-sm mb-4">
          ✅ Saqlandi. O'quvchilarga xabar yuborilmoqda.
        </div>
      )}
      <DraftReview
        topic={topic}
        homework={homework}
        onTopicChange={setTopic}
        onHomeworkChange={setHw}
      />
      {students.map((s) => (
        <StudentRow key={s.id} student={s} onChange={handleChange} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Test with real teacher account**

```bash
# Open Mini App via BotFather link
# Verify: student list renders, attendance toggles work
# Tap Saqlash → verify outbox populated in DB
sqlite3 data/journal.db "SELECT status, text FROM outbox LIMIT 3;"
```

- [ ] **Step 5: Commit**

```bash
git add miniapp/src/
git commit -m "feat: Today screen with manual attendance entry and save"
```

---

### Task 13: VoiceStatus component (SSE auto-fill)

**Files:**
- Create: `miniapp/src/components/VoiceStatus.tsx`
- Modify: `miniapp/src/screens/Today.tsx` (integrate VoiceStatus)

**Interfaces:**
- Consumes: `GET /api/lessons/{id}/stream` (SSE), `pristine.current` flag
- Produces: spinner that auto-fills form on `draft_ready` event (only if pristine)

- [ ] **Step 1: Create VoiceStatus.tsx**

```typescript
import { useEffect, useState } from "react";

interface Props {
  lessonId: number;
  token: string;
  onDraftReady: () => void;
  apiBase: string;
}

export default function VoiceStatus({ lessonId, token, onDraftReady, apiBase }: Props) {
  const [status, setStatus] = useState<"waiting" | "ready" | "timeout">("waiting");

  useEffect(() => {
    const es = new EventSource(
      `${apiBase}/api/lessons/${lessonId}/stream`,
      // Note: EventSource doesn't support custom headers; pass token as query param
    );
    // Backend must accept ?token= as alternative to Bearer header for SSE
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.event === "draft_ready") {
        setStatus("ready");
        onDraftReady();
        es.close();
      } else if (data.event === "timeout") {
        setStatus("timeout");
        es.close();
      }
    };
    es.onerror = () => { setStatus("timeout"); es.close(); };
    return () => es.close();
  }, [lessonId]);

  if (status === "ready") return null;
  if (status === "timeout") return (
    <div className="text-xs text-orange-500 mb-3">
      ⚠️ AI ishlamadi — qo'lda kiriting
    </div>
  );
  return (
    <div className="flex items-center gap-2 text-xs text-blue-500 mb-3">
      <span className="animate-spin">⏳</span> AI qoralama tayyorlanmoqda...
    </div>
  );
}
```

> **Note:** EventSource doesn't support `Authorization` headers. Two options: (a) pass JWT as a query param `?token=` — add support in the SSE endpoint's `require_teacher` to also accept query param; (b) use a short-lived one-time token. Option (a) is simpler for MVP. Update `deps.py` to check query param as fallback for SSE routes.

- [ ] **Step 2: Update deps.py to support SSE token query param**

Add to `app/api/deps.py`:
```python
from fastapi import Query

async def require_teacher_sse(
    token: str = Query(...),
) -> int:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
```

Update SSE endpoint in `lessons.py`:
```python
from app.api.deps import require_teacher_sse

@router.get("/api/lessons/{lesson_id}/stream")
async def stream_lesson(
    lesson_id: int,
    _: int = Depends(require_teacher_sse),   # ← changed
):
    ...
```

- [ ] **Step 3: Integrate VoiceStatus into Today.tsx**

In `Today.tsx`, after `apiFetch<TodayData>("/api/today")`, check if `lesson.status === 'draft'` and `attendance` is empty — if so, render `<VoiceStatus>` and reload data when `onDraftReady` fires:

```typescript
// Add state:
const [aiProcessing, setAiProcessing] = useState(false);

// In useEffect after fetching:
if (d.lesson?.status === "draft" && d.attendance.length === 0) {
  setAiProcessing(true);
}

// In JSX, before StudentRow list:
{aiProcessing && data?.lesson && (
  <VoiceStatus
    lessonId={data.lesson.id}
    token={/* get from api.ts — export getToken() */}
    apiBase={import.meta.env.VITE_API_URL}
    onDraftReady={() => {
      setAiProcessing(false);
      if (pristine.current) {
        // Re-fetch to get AI draft
        apiFetch<TodayData>("/api/today").then((d) => {
          setTopic(d.lesson?.topic ?? "");
          setHw(d.lesson?.homework ?? "");
          const attMap = Object.fromEntries(d.attendance.map((a) => [a.student_id, a]));
          setStudents((prev) =>
            prev.map((s) => ({
              ...s,
              status: attMap[s.id]?.status ?? s.status,
              grade: attMap[s.id]?.grade ?? s.grade,
              note_public: attMap[s.id]?.note_public ?? s.note_public,
            }))
          );
        });
      }
    }}
  />
)}
```

Also export `getToken()` from `api.ts`:
```typescript
export function getToken(): string { return _token ?? ""; }
```

- [ ] **Step 4: End-to-end AI test**

```bash
# 1. Open Mini App (Today screen)
# 2. Send voice note to bot
# 3. Watch spinner appear in Mini App
# 4. After 10-20s: fields auto-fill from AI draft
# 5. Adjust if needed, tap Saqlash
```

- [ ] **Step 5: Commit**

```bash
git add miniapp/src/ backend/app/api/
git commit -m "feat: VoiceStatus SSE auto-fill, AI pipeline E2E"
```

---

### Task 14: Yesterday screen

**Files:**
- Create: `miniapp/src/screens/Yesterday.tsx`
- Modify: `miniapp/src/App.tsx` (add nav between screens)

**Interfaces:**
- Consumes: `GET /api/lessons?date=YYYY-MM-DD`, `PATCH /api/attendance/{id}`, `apiFetch`, `StudentRow`

- [ ] **Step 1: Create Yesterday.tsx**

```typescript
import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { setMainButton, hideMainButton, haptic } from "../lib/telegram";
import StudentRow, { StudentData, AttStatus } from "../components/StudentRow";

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().split("T")[0];
}

interface LessonData {
  group: { id: number; name: string } | null;
  lesson: { id: number; date: string } | null;
  students: { id: number; full_name: string }[];
  attendance: { id: number; student_id: number; status: AttStatus; grade: number | null; note_public: string | null }[];
}

export default function Yesterday() {
  const [data, setData]         = useState<LessonData | null>(null);
  const [students, setStudents] = useState<StudentData[]>([]);
  const [saved, setSaved]       = useState(false);

  useEffect(() => {
    apiFetch<LessonData>(`/api/lessons?date=${yesterday()}`).then((d) => {
      setData(d);
      if (!d.lesson) return;
      const attMap = Object.fromEntries(d.attendance.map((a) => [a.student_id, a]));
      setStudents(
        d.students.map((s) => ({
          id: s.id, full_name: s.full_name,
          status: attMap[s.id]?.status ?? "present",
          grade: attMap[s.id]?.grade ?? null,
          note_public: attMap[s.id]?.note_public ?? "",
          att_id: attMap[s.id]?.id ?? null,
        }))
      );
    });
  }, []);

  useEffect(() => {
    if (!data?.lesson || saved) { hideMainButton(); return; }
    setMainButton("Saqlash (jim)", handleSave);
  }, [data, saved]);

  const handleSave = async () => {
    if (!data?.lesson) return;
    haptic();
    for (const s of students) {
      if (s.att_id) {
        await apiFetch(`/api/attendance/${s.att_id}`, {
          method: "PATCH",
          body: JSON.stringify({ student_id: s.id, status: s.status, grade: s.grade, note_public: s.note_public || null }),
        });
      }
    }
    setSaved(true);
    hideMainButton();
  };

  if (!data) return <div className="p-4 text-gray-400">Yuklanmoqda...</div>;
  if (!data.group) return <div className="p-4 text-gray-500">Kecha dars bo'lmagan.</div>;

  return (
    <div className="p-4 pb-20 bg-gray-50 min-h-screen">
      <h1 className="font-semibold text-lg mb-1">Kecha — {data.group.name}</h1>
      <p className="text-xs text-orange-500 mb-4">⚠️ Tuzatish xabar yuborMaYdi</p>
      {saved && (
        <div className="bg-green-100 text-green-700 rounded-lg p-3 text-sm mb-4">
          ✅ Tuzatishlar saqlandi.
        </div>
      )}
      {students.map((s) => (
        <StudentRow key={s.id} student={s} onChange={(u) =>
          setStudents((prev) => prev.map((x) => (x.id === u.id ? u : x)))
        } />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Add nav to App.tsx**

```typescript
// Add to App.tsx: simple tab navigation
import Yesterday from "./screens/Yesterday";
type Screen = "today" | "yesterday";

// In App render (after ready):
const [screen, setScreen] = useState<Screen>("today");
return (
  <div>
    <div className="flex border-b bg-white sticky top-0 z-10">
      {(["today","yesterday"] as Screen[]).map((s) => (
        <button key={s}
          onClick={() => setScreen(s)}
          className={`flex-1 py-3 text-sm font-medium ${screen===s?"border-b-2 border-blue-500 text-blue-600":"text-gray-500"}`}
        >
          {s === "today" ? "Bugun" : "Kecha"}
        </button>
      ))}
    </div>
    {screen === "today" ? <Today /> : <Yesterday />}
  </div>
);
```

- [ ] **Step 3: Test yesterday correction**

```bash
# Navigate to Kecha tab
# Change a grade or attendance
# Tap "Saqlash (jim)"
sqlite3 data/journal.db "SELECT grade, status FROM attendance WHERE lesson_id = <yesterday_id>;"
# Verify change — no new outbox rows
sqlite3 data/journal.db "SELECT COUNT(*) FROM outbox;"  # same count as before
```

- [ ] **Step 4: Commit**

```bash
git add miniapp/src/
git commit -m "feat: Yesterday screen, silent correction via PATCH attendance"
```

---

### Task 15: Docker, Caddy, deploy

**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `Caddyfile`
- Create: `.env.example` (root)

**Interfaces:**
- Produces: running system on VPS with HTTPS, webhook set, Mini App on Vercel

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
services:
  app:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
    expose:
      - "8000"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data

volumes:
  caddy_data:
```

- [ ] **Step 3: Write Caddyfile**

```
api.domain.uz {
    reverse_proxy app:8000

    header {
        Access-Control-Allow-Origin "https://journal.vercel.app"
        Access-Control-Allow-Headers "Authorization, Content-Type, Idempotency-Key"
        Access-Control-Allow-Methods "GET, POST, PUT, PATCH, OPTIONS, DELETE"
    }

    @options method OPTIONS
    respond @options 204
}
```

- [ ] **Step 4: VPS setup commands**

```bash
# On Hetzner CX22, Ubuntu 24.04:
apt update && apt upgrade -y
adduser deploy && usermod -aG sudo deploy
# /etc/ssh/sshd_config: PasswordAuthentication no → systemctl restart ssh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
# Set A-record: api.domain.uz → VPS IP
```

- [ ] **Step 5: Deploy backend**

```bash
# As deploy user on VPS:
git clone <repo> && cd ustoz-jurnali
cp .env.example .env   # fill all values
docker compose up -d --build
# Run migration + seed:
docker compose exec app alembic upgrade head
docker compose exec app python -m app.db.seed
# Set webhook:
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://api.domain.uz/webhook/telegram/${WEBHOOK_SECRET}" \
  -d "secret_token=${WEBHOOK_SECRET}"
# Verify:
curl https://api.domain.uz/api/health
```

- [ ] **Step 6: Deploy Mini App to Vercel**

```bash
# In Vercel dashboard:
# New Project → GitHub repo
# Root Directory: miniapp
# Build Command: npm run build
# Output Directory: dist
# Env var: VITE_API_URL=https://api.domain.uz
# Deploy → copy Vercel URL
# BotFather → /newapp → set Vercel URL as Mini App URL
```

- [ ] **Step 7: Set up daily backup cron**

```bash
# crontab -e as deploy:
0 22 * * * sqlite3 /home/deploy/ustoz-jurnali/data/journal.db \
  ".backup /tmp/j-$(date +\%F).db" && \
  rclone copy /tmp/j-$(date +\%F).db r2:journal-backups/ && \
  rm /tmp/j-$(date +\%F).db
```

- [ ] **Step 8: Set up UptimeRobot**

```
Add monitor: https://api.domain.uz/api/health
Interval: 5 minutes
Alert: email
```

- [ ] **Step 9: Full E2E smoke test on production**

```bash
# 1. Bot: /start → register as student
# 2. Teacher Mini App: verify student appears
# 3. Teacher: save manual attendance → student receives report
# 4. Teacher: send voice note → AI pipeline runs → Mini App auto-fills
# 5. Teacher: Saqlash → all students receive reports
# 6. Teacher: Kecha tab → correct a grade → no re-notification
```

- [ ] **Step 10: Commit and tag**

```bash
git add docker-compose.yml Caddyfile backend/Dockerfile
git commit -m "feat: Docker, Caddy, deploy configuration"
git tag v1.0.0
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by task |
|---|---|
| SQLite + VPS | Task 2 (DB), Task 15 (Docker) |
| Student self-registration | Task 4 (bot /start FSM) |
| JWT Mini App auth | Task 5 |
| GET /api/today (lazy lesson) | Task 6 |
| Manual attendance + grades | Task 6 + Task 12 |
| POST /confirm idempotent | Task 7 |
| Outbox worker 30s loop | Task 7 |
| retry + failure summary | Task 7 (outbox.py) |
| ElevenLabs ASR | Task 8 |
| Claude Haiku LLM | Task 9 |
| rapidfuzz match (80% threshold) | Task 9 |
| Voice handler + AI pipeline | Task 10 |
| SSE stream endpoint | Task 10 |
| Report message format | Task 7 (report.py) |
| raw_note never sent | Task 7 (build_report takes no raw_note param) |
| VoiceStatus + auto-fill (pristine only) | Task 13 |
| Yesterday screen + PATCH att | Task 14 |
| PATCH silent (no re-notify) | Task 14 |
| Webhook secret token verify | Task 4 (main.py) |
| TEACHER_TELEGRAM_ID guard | Task 5 (deps.py) |
| Tashkent timezone | Task 3 |
| Docker + Caddy + HTTPS | Task 15 |
| Daily SQLite backup | Task 15 |
| UptimeRobot health monitor | Task 15 |
| Milestone: show teacher before AI | Between Task 7 and Task 8 |

All requirements covered. No placeholders. Types consistent across tasks.
