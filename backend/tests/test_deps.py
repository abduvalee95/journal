import time
from fastapi import Depends
from fastapi.testclient import TestClient
from jose import jwt
from app.main import app
from app.api.deps import require_teacher
from app.config import settings

# A throwaway protected route mounted just for these tests, so require_teacher
# can be exercised end-to-end (through TestClient/HTTPBearer) before Task 6
# adds any real protected endpoints.
@app.get("/api/_test/protected")
async def _protected_route(teacher_id: int = Depends(require_teacher)):
    return {"teacher_id": teacher_id}

client = TestClient(app)


def _make_token(sub, secret=None, exp_offset_sec=1800):
    secret = settings.jwt_secret if secret is None else secret
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset_sec}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_token_returns_teacher_id():
    token = _make_token(str(settings.teacher_telegram_id))
    r = client.get("/api/_test/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"teacher_id": settings.teacher_telegram_id}


def test_missing_header_gets_401():
    r = client.get("/api/_test/protected")
    assert r.status_code == 401


def test_malformed_token_gets_401():
    r = client.get(
        "/api/_test/protected",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401


def test_expired_token_gets_401():
    token = _make_token(str(settings.teacher_telegram_id), exp_offset_sec=-10)
    r = client.get("/api/_test/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_wrong_secret_token_gets_401():
    token = _make_token(str(settings.teacher_telegram_id), secret="wrong-secret")
    r = client.get("/api/_test/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
