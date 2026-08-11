# Ustoz Jurnali — Design Spec

**Date:** 2026-08-11  
**Status:** Approved  
**Scope:** MVP v1 — single teacher, 6 groups, attendance + grading + AI-powered reports via Telegram Bot + Mini App

---

## 1. Overview

A Telegram Bot + Mini App for a language teacher to record daily attendance, grades, and lesson notes. After each class, the teacher sends a voice note (or enters data manually), the system processes it with AI, and sends a personalized report to each student via Telegram.

**Key constraints:**
- One teacher only
- 6 groups, one group per weekday (Mon–Sat)
- 8–15 students per group
- Voice note sent **after class**, one per lesson
- Student reports: class summary + personal grade (1–5) + personal note
- Completely separate from existing NestJS/Postgres project
- **Location:** Ош, Қирғизистон — timezone `Asia/Bishkek` (UTC+6)
- **UI language:** O'zbek tili, **Krill yozuvi** (barcha bot xabarlari va Mini App matni)

---

## 2. Infrastructure

| Component | Choice | Reason |
|---|---|---|
| Backend | Python 3.12 + FastAPI + aiogram 3 on Hetzner CX22 (~€4.35/mo) | No cold start, SQLite file persistence, no time limits on AI pipeline |
| Database | SQLite (`journal.db`) | ~5K rows/year, single writer, no network, zero ops |
| Frontend | React 18 + TypeScript + Vite on Vercel (free) | Static build, HTTPS auto, git push = deploy |
| Reverse proxy | Caddy 2 | Auto HTTPS, CORS config, zero cert management |
| ASR | ElevenLabs Scribe | Lowest Uzbek WER (~3.1%), ~$0.22/hour |
| LLM | Claude Haiku (structured JSON output) | Cheap, fast, reliable schema adherence |
| Container | Docker + Compose | Reproducible, `restart: unless-stopped` |

**Cost: ~$6/month** (VPS €4.35 + AI ~$0.50 + domain ~$1)

**Alternative if VPS is undesirable:** Vercel Python Functions + Neon Postgres + Vercel Cron — works but adds cold starts, external DB latency, and more complex architecture. Not recommended.

---

## 3. Database Schema

```sql
CREATE TABLE groups (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    weekday     INTEGER NOT NULL,   -- 1=Mon ... 6=Sat
    start_time  TEXT,               -- "18:00"
    is_active   INTEGER NOT NULL DEFAULT 1,
    UNIQUE(weekday, is_active)
);

CREATE TABLE students (
    id          INTEGER PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES groups(id),
    full_name   TEXT    NOT NULL,
    telegram_id INTEGER UNIQUE NOT NULL,  -- set at registration
    joined_at   TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_students_group ON students(group_id, is_active);

CREATE TABLE lessons (
    id             INTEGER PRIMARY KEY,
    group_id       INTEGER NOT NULL REFERENCES groups(id),
    lesson_date    TEXT    NOT NULL,   -- "YYYY-MM-DD", Tashkent time
    topic          TEXT,
    raw_note       TEXT,               -- voice transcript — NEVER sent to students
    audio_file_id  TEXT,
    summary_public TEXT,               -- AI-generated, shown to students
    homework       TEXT,
    status         TEXT NOT NULL DEFAULT 'draft',  -- draft | saved
    saved_at       TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE(group_id, lesson_date)
);

CREATE TABLE attendance (
    id           INTEGER PRIMARY KEY,
    lesson_id    INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    student_id   INTEGER NOT NULL REFERENCES students(id),
    status       TEXT    NOT NULL,   -- present | absent | late
    grade        INTEGER,            -- 1..5, NULL if absent
    note_public  TEXT,               -- sent to student
    note_private TEXT,               -- teacher-only, never sent
    notified_at  TEXT,
    UNIQUE(lesson_id, student_id),
    CHECK (grade IS NULL OR grade BETWEEN 1 AND 5)
);

CREATE TABLE outbox (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id),
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id),
    text        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT    NOT NULL,
    sent_at     TEXT
);
CREATE INDEX idx_outbox_pending ON outbox(status, created_at);

CREATE TABLE ai_jobs (
    id          INTEGER PRIMARY KEY,
    lesson_id   INTEGER REFERENCES lessons(id),
    stage       TEXT,        -- asr | llm
    status      TEXT,        -- running | done | error
    duration_ms INTEGER,
    error       TEXT,
    created_at  TEXT NOT NULL
);
```

**Notes:**
- No `invite_token` per student — students self-register via bot
- No `join_token` per group — open registration
- All dates stored as ISO strings in Asia/Bishkek time
- `raw_note` and `note_private` never appear in any student-facing API response (enforced by separate Pydantic output schemas)

---

## 4. Student Registration Flow

```
Student sends any message or /start to bot
  → bot: "Исмингиз ва фамилиянгиз?"
  → student types name
  → bot shows group selection (inline keyboard, active groups only)
  → student selects group
  → INSERT INTO students (telegram_id, full_name, group_id, joined_at)
  → bot: "Рўйхатдан ўтдингиз! Дарс ҳисоботлари шу ерга келади."
```

If student already registered → bot: "Сиз аллақачон рўйхатдасиз: [ism]"

---

## 5. AI Pipeline (Voice → Draft)

```
1. Teacher sends voice note to bot
2. Bot identifies today's group: groups WHERE weekday = tashkent_weekday()
3. Download .oga file from Telegram (getFile)
4. ai_jobs INSERT stage=asr, status=running
5. POST ElevenLabs Scribe: { model_id: "scribe_v1", language_code: "uzb", file }
   → transcript → lessons.raw_note
6. ai_jobs UPDATE stage=llm, status=running
7. POST Claude Haiku with:
   - system: strict JSON schema + privacy rules
   - user: transcript + THIS group's student list (names only)
   → JSON: { topic, summary_public, homework, per_student[] }
8. rapidfuzz match: per_student[].name_mentioned → students in this group (threshold 80%)
   - no match → shown to teacher with "?" marker
9. lessons.status = 'draft', ai_jobs status = done
10. Bot → teacher: "✅ Qoralama tayyor — Mini App'da ko'ring"
    SSE endpoint notifies if Mini App is open
```

**LLM output schema:**
```json
{
  "topic": "string",
  "summary_public": "string — no criticism, no student comparisons",
  "homework": "string",
  "per_student": [
    {
      "name_mentioned": "string",
      "note_public": "string — supportive tone, AI softens harsh raw notes",
      "grade_suggested": 1..5,
      "attendance_hint": "present | absent | late"
    }
  ]
}
```

`grade_suggested` is a suggestion only. Teacher sets the final grade in Mini App. AI does not set grades.

**If AI fails:** `ai_jobs` status=error, teacher notified "AI ishlamadi, qo'lda kiriting", empty form shown in Mini App.

**Alternative considered:** Gemini Flash (single API call, audio direct input). Lower Uzbek accuracy. Recommended to test both with teacher's actual voice before committing.

---

## 6. Mini App

**Authentication:**
```
Telegram.WebApp.initData → POST /api/auth/telegram
  server validates: HMAC-SHA256, auth_date < 5min, user.id == TEACHER_TELEGRAM_ID
  → JWT (30 min), stored in memory (not localStorage)
  → all /api/* requests: Authorization: Bearer <JWT>
```

**Screens:**

**Today (`/`):**
- `GET /api/today` → group name + date + student list + existing draft/attendance
  - If no lesson record exists for today, one is created lazily (`status='draft'`, fields empty)
- One `StudentRow` per student: `[Name] [present|absent|late] [1][2][3][4][5] [note...]`
- If AI draft exists: fields pre-filled from AI suggestions (editable)
- If AI is processing: SSE `/api/lessons/{id}/stream` → spinner → auto-fills on completion (only if form is pristine — no manual changes made yet)
- Topic + homework fields (editable)
- `MainButton` "Saqlash" → `POST /api/lessons/{id}/confirm` with `Idempotency-Key`
  - Only works if `status = 'draft'` (idempotent, double-tap safe)
  - On success: `status = 'saved'`, outbox populated, MainButton disabled

**Yesterday (`/yesterday`):**
- `GET /api/lessons?date=yesterday`
- Same `StudentRow` layout, editable
- `PATCH /api/attendance/{id}` — saves silently, NO re-notification to students
- Useful for correcting errors without spamming students

---

## 7. Student Report Message Format

```
📚 [Гуруҳ номи] — [11 август 2026]
Мавзу: [topic]

[summary_public]

---
✅ Даводим: Келдингиз          (ёки ❌ Келмадингиз / 🕐 Кеч келдингиз)
⭐ Баҳо: 4/5                   (йўқ, агар келмаган бўлса)
💬 [note_public]               (йўқ, агар бўш бўлса)

📝 Уй вазифаси: [homework]     (йўқ, агар бўш бўлса)
```

Privacy rules (enforced in code):
- `raw_note` never included
- `note_private` never included
- No other student's name in the message
- No comparisons or criticism

---

## 8. Outbox Worker

`asyncio.create_task()` started in FastAPI `lifespan`, runs every 30 seconds:

```python
SELECT * FROM outbox WHERE status='pending' ORDER BY created_at
FOR EACH row:
  sendMessage(student.telegram_id, row.text)
  SUCCESS → status=sent, sent_at=now
  TelegramForbiddenError → status=failed, last_error=...
  other error + attempts < 3 → attempts++, retry next cycle
  other error + attempts >= 3 → status=failed
DAILY (if any failed today) → send teacher summary: "N ta xabar yetmadi"
```

---

## 9. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhook/telegram/{secret}` | Telegram updates |
| `POST` | `/api/auth/telegram` | initData → JWT |
| `GET` | `/api/today` | Today's group + students + existing attendance |
| `GET` | `/api/lessons?date=YYYY-MM-DD` | Past lesson (yesterday screen) |
| `PUT` | `/api/lessons/{id}/attendance` | Save attendance + grades (batch) |
| `PATCH` | `/api/lessons/{id}` | Edit topic/homework |
| `GET` | `/api/lessons/{id}/stream` | SSE: AI processing status |
| `POST` | `/api/lessons/{id}/confirm` | Finalize → populate outbox (idempotent) |
| `PATCH` | `/api/attendance/{id}` | Silent correction (no re-notification) |
| `GET` | `/api/health` | Monitoring |

---

## 10. Project Structure

```
ustoz-jurnali/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + aiogram webhook + lifespan
│   │   ├── config.py            # Pydantic Settings (.env)
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   ├── session.py
│   │   │   └── seed.py          # 6 groups only (no students — they self-register)
│   │   ├── bot/
│   │   │   ├── handlers/
│   │   │   │   ├── start.py     # registration flow
│   │   │   │   ├── voice.py     # voice → AI pipeline
│   │   │   │   └── confirm.py   # Saqlash/Tahrirlash inline buttons
│   │   │   └── keyboards.py
│   │   ├── api/
│   │   │   ├── auth.py          # initData validation + JWT
│   │   │   ├── lessons.py       # today, yesterday, confirm, SSE stream
│   │   │   └── deps.py          # JWT guard (teacher only)
│   │   ├── services/
│   │   │   ├── asr.py           # ElevenLabs Scribe
│   │   │   ├── llm.py           # Claude Haiku structured output
│   │   │   ├── matcher.py       # rapidfuzz name matching
│   │   │   ├── report.py        # build student message text
│   │   │   └── outbox.py        # asyncio worker + retry logic
│   │   └── utils/
│   │       └── localtime.py      # Asia/Bishkek helpers, today(), weekday()
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── miniapp/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── screens/
│   │   │   ├── Today.tsx
│   │   │   └── Yesterday.tsx
│   │   ├── components/
│   │   │   ├── StudentRow.tsx   # attendance toggle + grade selector + note
│   │   │   ├── VoiceStatus.tsx  # SSE spinner → auto-fill
│   │   │   └── DraftReview.tsx  # topic + homework fields
│   │   └── lib/
│   │       ├── telegram.ts      # SDK, MainButton, HapticFeedback, themeParams
│   │       └── api.ts           # JWT fetch wrapper
│   ├── vite.config.ts
│   └── package.json
├── docker-compose.yml
├── Caddyfile
└── .env.example
```

---

## 11. Security

- Webhook URL contains 32-char random `secret_token`; Telegram sends it as `X-Telegram-Bot-Api-Secret-Token` header — verified on every request
- Mini App: `initData` HMAC-SHA256 validated server-side; `auth_date` checked < 5 min old; only `TEACHER_TELEGRAM_ID` can access `/api/*`
- `TeacherLessonOut` Pydantic schema includes `raw_note` and `note_private`
- `StudentReportOut` Pydantic schema excludes both — different schema used in `report.py`
- No student-facing API endpoints at all (students only receive bot messages)

---

## 12. Deployment

See original plan §9 for full VPS setup commands. Summary:
- Hetzner CX22, Ubuntu 24.04, SSH key only
- UFW: ports 22, 80, 443
- Docker + Compose, `restart: unless-stopped`
- Caddy handles HTTPS + CORS
- SQLite volume-mounted at `./data/journal.db`
- Daily backup via cron: `sqlite3 .backup` → rclone → R2/S3
- Webhook set once after deploy
- Vercel for Mini App: `Root=miniapp`, `Build=npm run build`, `Output=dist`
- UptimeRobot monitors `/api/health` (free)

---

## 13. Environment Variables

```bash
BOT_TOKEN=
WEBHOOK_SECRET=          # 32 random chars
TEACHER_TELEGRAM_ID=
BASE_URL=https://api.domain.uz
MINIAPP_URL=https://journal.vercel.app
JWT_SECRET=              # 32 random chars
DATABASE_URL=sqlite+aiosqlite:///./data/journal.db
ELEVENLABS_API_KEY=
LLM_API_KEY=             # Anthropic
LLM_MODEL=claude-haiku-4-5-20251001
TZ=Asia/Bishkek
```

---

## 14. Build Order

| # | Milestone | Deliverable | Est. |
|---|---|---|---|
| 0 | Prep | BotFather bot, API keys, Hetzner account, domain, GitHub repo | 1h |
| 1 | Skeleton | FastAPI + aiogram, ngrok webhook locally, `/start` replies | 2h |
| 2 | DB + Groups | Models, Alembic migration, seed 6 groups | 1h |
| 3 | Registration | Student self-registration flow (name + group) | 2h |
| 4 | Auth + Today screen | initData JWT, Mini App renders student list, manual attendance save | 4h |
| **5** | **Stop & show teacher** | **Manual attendance works — already useful without AI** | — |
| 6 | AI pipeline | Voice → Scribe → LLM → draft → SSE → Mini App auto-fill | 6h |
| 7 | Outbox + reports | Student receives message, retry logic, failure summary | 4h |
| 8 | Yesterday screen | Silent correction flow | 2h |
| 9 | Deploy | VPS, Docker, Caddy, webhook, backup, Vercel | 3h |
| 10 | Real test | 1 week with teacher, collect issues | 1 week |

---

## 15. Out of Scope (v1)

Payment tracking, homework submission, parent notifications, AI trend analysis, group stats dashboard, full calendar, lesson cancellation/rescheduling, daily reminders to teacher, group/student management UI, multi-teacher support.
