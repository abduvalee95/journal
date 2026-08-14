import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

router = APIRouter()

# Telegram refuses to hand the Mini App a fresh initData while it stays open,
# and _verify() rejects an auth_date older than 5 minutes -- so re-running the
# initData exchange is not a way back from an expired session. The token is
# short-lived and renewed through /api/auth/refresh instead.
TOKEN_TTL_SECONDS = 1800
AUDIENCE = "ustoz-miniapp"

_bearer = HTTPBearer(auto_error=False)


class InitDataReq(BaseModel):
    init_data: str


def issue_token(user_id: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + TOKEN_TTL_SECONDS,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    """Decode a session token, or raise 401.

    `algorithms` is pinned so `alg: none` and HS/RS confusion are both refused,
    and `audience` is checked so a token minted from JWT_SECRET for some other
    purpose cannot be replayed here.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=AUDIENCE,
        )
    except JWTError:
        raise HTTPException(401, "Invalid token")
    # python-jose accepts a token that carries no `aud` at all even when an
    # audience is expected -- it only rejects a *wrong* one. Require it here,
    # or a token minted from JWT_SECRET for anything else still gets in.
    if payload.get("aud") != AUDIENCE:
        raise HTTPException(401, "Invalid token")
    return payload


def _verify(init_data: str) -> dict:
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received = params.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise HTTPException(401, "Invalid signature")
    try:
        auth_date = int(params.get("auth_date", 0))
    except ValueError:
        raise HTTPException(401, "Invalid auth_date")
    if time.time() - auth_date > 300:
        raise HTTPException(401, "auth_date expired")
    return params


@router.post("/api/auth/telegram")
async def auth_telegram(body: InitDataReq):
    params = _verify(body.init_data)
    try:
        user = json.loads(params.get("user", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(401, "Invalid user payload")
    if not isinstance(user, dict):
        raise HTTPException(401, "Invalid user payload")
    if user.get("id") != settings.teacher_telegram_id:
        raise HTTPException(403, "Not authorized")
    return {"access_token": issue_token(user["id"]), "expires_in": TOKEN_TTL_SECONDS}


@router.post("/api/auth/refresh")
async def refresh_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Exchange a still-valid session token for a fresh one.

    Without this a lesson longer than the token lifetime ends with every save
    returning 401 and no way back: the Mini App cannot re-run the initData
    exchange, so the teacher's only option would be to close the app, which
    discards everything they typed.
    """
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    sub = payload.get("sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token")
    if user_id != settings.teacher_telegram_id:
        raise HTTPException(403, "Not authorized")
    return {"access_token": issue_token(user_id), "expires_in": TOKEN_TTL_SECONDS}
