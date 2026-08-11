"""
Verification tests for Task 6: today/date-lookup/attendance-save API.

The brief's own verification step (curl with a real Telegram initData) is
not available in this environment, so these tests drive the endpoints
through real HTTP (TestClient) against a real, isolated SQLite database
(created fresh per test), asserting on actual DB rows rather than mocks.
"""
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.config import settings
from app.db.models import Base, Group, Student, Lesson, Attendance
from app.db.session import get_session

# A fixed "today" used by every test that needs a deterministic weekday --
# 2026-08-10 is a Monday (isoweekday 1). Tests patch app.api.lessons.today /
# .weekday directly, since lessons.py imported those names with
# `from ... import today, weekday`, binding them locally at import time.
FIXED_DATE = "2026-08-10"
FIXED_WEEKDAY = 1


def _make_token(sub) -> str:
    payload = {"sub": str(sub), "exp": int(time.time()) + 1800}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


AUTH_HEADERS = {"Authorization": f"Bearer {_make_token(settings.teacher_telegram_id)}"}


@pytest.fixture
async def db(tmp_path):
    """Isolated SQLite DB wired into the app's get_session dependency, so
    every request made through TestClient in a test hits this throwaway
    database instead of backend/data/journal.db. Yields the session_maker
    so tests can seed data and assert on rows directly."""
    db_path = tmp_path / "test_lessons.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@pytest.fixture
def client(db):
    # No `with` block: keeps Starlette from running the lifespan (which
    # would try to register a real Telegram webhook), same pattern as
    # test_bot_registration.py / test_deps.py.
    return TestClient(app)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

async def _seed_group(db, *, weekday=FIXED_WEEKDAY, is_active=1, name="Beginners A") -> Group:
    async with db() as s:
        g = Group(name=name, weekday=weekday, start_time="09:00", is_active=is_active)
        s.add(g)
        await s.commit()
        await s.refresh(g)
        return g


async def _seed_student(db, group_id, *, full_name="Ali Valiyev", telegram_id=1001, is_active=1) -> Student:
    async with db() as s:
        st = Student(
            group_id=group_id, full_name=full_name, telegram_id=telegram_id,
            joined_at="2026-01-01T00:00:00+06:00", is_active=is_active,
        )
        s.add(st)
        await s.commit()
        await s.refresh(st)
        return st


async def _seed_lesson(db, group_id, *, lesson_date=FIXED_DATE) -> Lesson:
    async with db() as s:
        lesson = Lesson(group_id=group_id, lesson_date=lesson_date, created_at="2026-08-10T09:00:00+06:00")
        s.add(lesson)
        await s.commit()
        await s.refresh(lesson)
        return lesson


async def _seed_attendance(db, lesson_id, student_id, **kwargs) -> Attendance:
    async with db() as s:
        att = Attendance(lesson_id=lesson_id, student_id=student_id, **kwargs)
        s.add(att)
        await s.commit()
        await s.refresh(att)
        return att


# ---------------------------------------------------------------------------
# GET /api/today
# ---------------------------------------------------------------------------

async def test_today_with_active_group_creates_lesson_and_returns_roster(client, db, monkeypatch):
    monkeypatch.setattr("app.api.lessons.weekday", lambda: FIXED_WEEKDAY)
    monkeypatch.setattr("app.api.lessons.today", lambda: FIXED_DATE)

    group = await _seed_group(db)
    student = await _seed_student(db, group.id)

    r = client.get("/api/today", headers=AUTH_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == {"id": group.id, "name": "Beginners A"}
    assert body["lesson"]["date"] == FIXED_DATE
    assert body["lesson"]["status"] == "draft"
    assert body["lesson"]["topic"] is None
    assert body["students"] == [{"id": student.id, "full_name": "Ali Valiyev"}]
    assert body["attendance"] == []

    async with db() as s:
        lessons = (await s.execute(select(Lesson).where(Lesson.group_id == group.id))).scalars().all()
    assert len(lessons) == 1
    assert lessons[0].lesson_date == FIXED_DATE


async def test_today_called_twice_does_not_duplicate_lesson(client, db, monkeypatch):
    monkeypatch.setattr("app.api.lessons.weekday", lambda: FIXED_WEEKDAY)
    monkeypatch.setattr("app.api.lessons.today", lambda: FIXED_DATE)

    group = await _seed_group(db)

    r1 = client.get("/api/today", headers=AUTH_HEADERS)
    r2 = client.get("/api/today", headers=AUTH_HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["lesson"]["id"] == r2.json()["lesson"]["id"]

    async with db() as s:
        lessons = (await s.execute(select(Lesson).where(Lesson.group_id == group.id))).scalars().all()
    assert len(lessons) == 1


async def test_today_with_no_active_group_returns_empty_shape(client, db, monkeypatch):
    monkeypatch.setattr("app.api.lessons.weekday", lambda: FIXED_WEEKDAY)
    monkeypatch.setattr("app.api.lessons.today", lambda: FIXED_DATE)

    # An inactive group on the same weekday must not be picked up.
    await _seed_group(db, is_active=0, name="Inactive Monday Group")

    r = client.get("/api/today", headers=AUTH_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"group": None, "lesson": None, "students": [], "attendance": []}

    async with db() as s:
        lessons = (await s.execute(select(Lesson))).scalars().all()
    assert lessons == []


def test_today_requires_auth(client, db):
    r = client.get("/api/today")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/lessons?date=YYYY-MM-DD
# ---------------------------------------------------------------------------

async def test_get_lesson_by_date_found(client, db):
    group = await _seed_group(db)
    lesson = await _seed_lesson(db, group.id, lesson_date="2026-08-10")

    r = client.get("/api/lessons", params={"date": "2026-08-10"}, headers=AUTH_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == {"id": group.id, "name": "Beginners A"}
    assert body["lesson"]["id"] == lesson.id
    assert body["lesson"]["date"] == "2026-08-10"


def test_get_lesson_by_date_not_found_returns_empty_shape(client, db):
    r = client.get("/api/lessons", params={"date": "2099-01-01"}, headers=AUTH_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"group": None, "lesson": None, "students": [], "attendance": []}


def test_get_lesson_by_date_requires_auth(client, db):
    r = client.get("/api/lessons", params={"date": "2026-08-10"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/lessons/{lesson_id}/attendance
# ---------------------------------------------------------------------------

async def test_put_attendance_inserts_then_updates_in_place(client, db):
    group = await _seed_group(db)
    student = await _seed_student(db, group.id)
    lesson = await _seed_lesson(db, group.id)

    r = client.put(
        f"/api/lessons/{lesson.id}/attendance",
        json={"items": [{"student_id": student.id, "status": "present", "grade": 4, "note_public": "Yaxshi"}]},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    async with db() as s:
        rows = (await s.execute(select(Attendance).where(Attendance.lesson_id == lesson.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "present"
    assert rows[0].grade == 4
    assert rows[0].note_public == "Yaxshi"

    # Second call with changed values must update the existing row, not
    # insert a duplicate.
    r2 = client.put(
        f"/api/lessons/{lesson.id}/attendance",
        json={"items": [{"student_id": student.id, "status": "late", "grade": 2, "note_public": None}]},
        headers=AUTH_HEADERS,
    )
    assert r2.status_code == 200

    async with db() as s:
        rows = (await s.execute(select(Attendance).where(Attendance.lesson_id == lesson.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "late"
    assert rows[0].grade == 2
    assert rows[0].note_public is None


async def test_put_attendance_topic_and_homework_persist_and_omission_preserves(client, db):
    group = await _seed_group(db)
    lesson = await _seed_lesson(db, group.id)

    r = client.put(
        f"/api/lessons/{lesson.id}/attendance",
        json={"items": [], "topic": "Present Perfect", "homework": "Ex. 5"},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 200

    async with db() as s:
        refreshed = await s.get(Lesson, lesson.id)
        assert refreshed.topic == "Present Perfect"
        assert refreshed.homework == "Ex. 5"

    # Omitting topic/homework (None) on a later call must leave the
    # existing values untouched, not clear them.
    r2 = client.put(
        f"/api/lessons/{lesson.id}/attendance",
        json={"items": []},
        headers=AUTH_HEADERS,
    )
    assert r2.status_code == 200

    async with db() as s:
        refreshed = await s.get(Lesson, lesson.id)
        assert refreshed.topic == "Present Perfect"
        assert refreshed.homework == "Ex. 5"


def test_put_attendance_unknown_lesson_returns_404(client, db):
    r = client.put("/api/lessons/99999/attendance", json={"items": []}, headers=AUTH_HEADERS)
    assert r.status_code == 404


def test_put_attendance_requires_auth(client, db):
    r = client.put("/api/lessons/1/attendance", json={"items": []})
    assert r.status_code == 401


def test_put_attendance_invalid_status_returns_422(client, db):
    r = client.put(
        "/api/lessons/1/attendance",
        json={"items": [{"student_id": 1, "status": "presnt"}]},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.parametrize("grade", [0, 6, -1, 9])
def test_put_attendance_invalid_grade_returns_422(client, db, grade):
    r = client.put(
        "/api/lessons/1/attendance",
        json={"items": [{"student_id": 1, "status": "present", "grade": grade}]},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/attendance/{att_id}
# ---------------------------------------------------------------------------

async def test_patch_attendance_updates_single_row(client, db):
    group = await _seed_group(db)
    student = await _seed_student(db, group.id)
    lesson = await _seed_lesson(db, group.id)
    att = await _seed_attendance(db, lesson.id, student.id, status="present", grade=3)

    r = client.patch(
        f"/api/attendance/{att.id}",
        json={"student_id": student.id, "status": "absent", "grade": None, "note_public": "Kasal"},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    async with db() as s:
        refreshed = await s.get(Attendance, att.id)
        assert refreshed.status == "absent"
        assert refreshed.grade is None
        assert refreshed.note_public == "Kasal"


def test_patch_unknown_attendance_returns_404(client, db):
    r = client.patch(
        "/api/attendance/99999",
        json={"student_id": 1, "status": "present", "grade": None},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 404


def test_patch_attendance_requires_auth(client, db):
    r = client.patch("/api/attendance/1", json={"student_id": 1, "status": "present", "grade": None})
    assert r.status_code == 401


def test_patch_attendance_invalid_status_returns_422(client, db):
    r = client.patch(
        "/api/attendance/1",
        json={"student_id": 1, "status": "not-a-status", "grade": None},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 422


def test_patch_attendance_invalid_grade_returns_422(client, db):
    r = client.patch(
        "/api/attendance/1",
        json={"student_id": 1, "status": "present", "grade": 10},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 422
