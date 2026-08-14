import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

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

def test_malformed_auth_date_gets_401():
    # auth_date present but non-numeric, with a correctly computed signature
    # for that exact payload -- must fail parsing (401), not crash (500).
    user = json.dumps({"id": settings.teacher_telegram_id, "first_name": "Test"})
    params = {"auth_date": "not-a-number", "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    init_data = f"auth_date=not-a-number&user={user}&hash={h}"
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401

def test_malformed_user_json_gets_401():
    # user field is present and correctly signed, but is not valid JSON at
    # all -- json.loads must fail parsing (401), not crash (500).
    auth_date = str(int(time.time()))
    user_raw = "not-json-at-all"
    params = {"auth_date": auth_date, "user": user_raw}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    init_data = f"auth_date={auth_date}&user={user_raw}&hash={h}"
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401

def test_non_dict_user_json_gets_401():
    # user field is valid JSON but not an object -- user.get("id") would
    # otherwise raise AttributeError (500) instead of a clean 401.
    auth_date = str(int(time.time()))
    user_raw = json.dumps([1, 2, 3])
    params = {"auth_date": auth_date, "user": user_raw}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    init_data = f"auth_date={auth_date}&user={user_raw}&hash={h}"
    r = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401
