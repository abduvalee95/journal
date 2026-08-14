import time

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AUDIENCE, issue_token
from app.api.deps import require_teacher
from app.config import settings

# A local app rather than the production singleton: mounting a test-only route
# on the imported `app` leaves it registered for every other test module in the
# session.
_app = FastAPI()


@_app.get("/api/_test/protected")
async def _protected_route(teacher_id: int = Depends(require_teacher)):
    return {"teacher_id": teacher_id}


client = TestClient(_app)


def _make_token(sub, secret=None, exp_offset_sec=1800, aud=AUDIENCE):
    secret = settings.jwt_secret if secret is None else secret
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset_sec}
    if aud is not None:
        payload["aud"] = aud
    return jwt.encode(payload, secret, algorithm="HS256")


def _get(token: str):
    return client.get("/api/_test/protected", headers={"Authorization": f"Bearer {token}"})


def test_valid_token_returns_teacher_id():
    r = _get(issue_token(settings.teacher_telegram_id))
    assert r.status_code == 200
    assert r.json() == {"teacher_id": settings.teacher_telegram_id}


def test_missing_header_gets_401():
    r = client.get("/api/_test/protected")
    assert r.status_code == 401


def test_malformed_token_gets_401():
    r = _get("not-a-real-jwt")
    assert r.status_code == 401


def test_expired_token_gets_401():
    r = _get(_make_token(str(settings.teacher_telegram_id), exp_offset_sec=-10))
    assert r.status_code == 401


def test_wrong_secret_token_gets_401():
    r = _get(_make_token(str(settings.teacher_telegram_id), secret="wrong-secret-value"))
    assert r.status_code == 401


def test_token_for_another_user_gets_403():
    """The guard checks the subject itself rather than trusting that auth.py is
    the only thing that ever mints a token from JWT_SECRET."""
    r = _get(issue_token(settings.teacher_telegram_id + 1))
    assert r.status_code == 403


def test_token_without_audience_gets_401():
    """A token signed with JWT_SECRET for any other purpose must not be
    accepted here. python-jose, which this used to use, quietly allowed a
    missing `aud` even when an audience was expected."""
    r = _get(_make_token(str(settings.teacher_telegram_id), aud=None))
    assert r.status_code == 401


def test_token_for_another_audience_gets_401():
    r = _get(_make_token(str(settings.teacher_telegram_id), aud="some-other-service"))
    assert r.status_code == 401
