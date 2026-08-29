"""Tests for groups and students management API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import issue_token
from app.config import settings
from app.db.models import Base
from app.db.session import get_session
from app.main import app


def _make_token(sub) -> str:
    return issue_token(sub)


AUTH_HEADERS = {"Authorization": f"Bearer {_make_token(settings.teacher_telegram_id)}"}
OTHER_HEADERS = {"Authorization": f"Bearer {_make_token(12345)}"}


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "test_groups.db"
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
def client():
    return TestClient(app)


# ── Auth Tests ───────────────────────────────────────────────


def test_groups_require_auth(client):
    res = client.get("/api/groups")
    assert res.status_code == 401

    res = client.get("/api/groups", headers=OTHER_HEADERS)
    assert res.status_code == 403


# ── Group CRUD Tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_and_create_groups(client, db):
    # Initial list is empty
    res = client.get("/api/groups", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == []

    # Create a group
    payload = {"name": "Monday Advanced", "weekday": 1, "start_time": "18:00"}
    res = client.post("/api/groups", json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == "Monday Advanced"
    assert created["weekday"] == 1
    assert created["start_time"] == "18:00"
    assert created["is_active"] == 1
    assert created["student_count"] == 0

    # List now shows the group
    res = client.get("/api/groups", headers=AUTH_HEADERS)
    assert res.status_code == 200
    groups = res.json()
    assert len(groups) == 1
    assert groups[0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_create_duplicate_weekday_rejected(client, db):
    client.post(
        "/api/groups",
        json={"name": "Group A", "weekday": 2, "start_time": "10:00"},
        headers=AUTH_HEADERS,
    )
    # Attempt to create another active group on weekday 2
    res = client.post(
        "/api/groups",
        json={"name": "Group B", "weekday": 2, "start_time": "14:00"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "faol guruh allaqachon mavjud" in res.json()["detail"]


@pytest.mark.asyncio
async def test_get_group_detail_and_update(client, db):
    res = client.post(
        "/api/groups",
        json={"name": "Initial Name", "weekday": 3, "start_time": "15:00"},
        headers=AUTH_HEADERS,
    )
    group_id = res.json()["id"]

    # Add a student to group
    s_res = client.post(
        f"/api/groups/{group_id}/students",
        json={"full_name": "Aziza Karimova"},
        headers=AUTH_HEADERS,
    )
    assert s_res.status_code == 201
    student = s_res.json()
    assert student["full_name"] == "Aziza Karimova"

    # Detail
    res = client.get(f"/api/groups/{group_id}", headers=AUTH_HEADERS)
    assert res.status_code == 200
    detail = res.json()
    assert detail["name"] == "Initial Name"
    assert len(detail["students"]) == 1
    assert detail["students"][0]["full_name"] == "Aziza Karimova"

    # Update group name and time
    res = client.patch(
        f"/api/groups/{group_id}",
        json={"name": "Updated Name", "start_time": "16:00"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Name"
    assert res.json()["start_time"] == "16:00"


@pytest.mark.asyncio
async def test_delete_group_soft_deletes(client, db):
    res = client.post(
        "/api/groups",
        json={"name": "To Archive", "weekday": 4, "start_time": "11:00"},
        headers=AUTH_HEADERS,
    )
    group_id = res.json()["id"]

    res = client.delete(f"/api/groups/{group_id}", headers=AUTH_HEADERS)
    assert res.status_code == 200

    # Not in default active list
    res = client.get("/api/groups", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Visible with include_inactive=true
    res = client.get("/api/groups?include_inactive=true", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["is_active"] == 0


# ── Student Management Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_student_management(client, db):
    # Create group 1 and group 2
    g1 = client.post(
        "/api/groups",
        json={"name": "Group 1", "weekday": 5, "start_time": "09:00"},
        headers=AUTH_HEADERS,
    ).json()
    g2 = client.post(
        "/api/groups",
        json={"name": "Group 2", "weekday": 6, "start_time": "12:00"},
        headers=AUTH_HEADERS,
    ).json()

    # Add student to g1
    st = client.post(
        f"/api/groups/{g1['id']}/students",
        json={"full_name": "Bobur Mirzo", "telegram_id": 999888777},
        headers=AUTH_HEADERS,
    ).json()
    student_id = st["id"]

    # Check student_count in g1
    groups = client.get("/api/groups", headers=AUTH_HEADERS).json()
    g1_found = next(g for g in groups if g["id"] == g1["id"])
    assert g1_found["student_count"] == 1

    # Update student name and move to g2
    res = client.patch(
        f"/api/students/{student_id}",
        json={"full_name": "Bobur Mirzo Updated", "group_id": g2["id"]},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    updated_st = res.json()
    assert updated_st["full_name"] == "Bobur Mirzo Updated"
    assert updated_st["group_id"] == g2["id"]

    # Deactivate student
    res = client.delete(f"/api/students/{student_id}", headers=AUTH_HEADERS)
    assert res.status_code == 200

    # Student count in g2 should be 0 active
    groups = client.get("/api/groups", headers=AUTH_HEADERS).json()
    g2_found = next(g for g in groups if g["id"] == g2["id"])
    assert g2_found["student_count"] == 0
