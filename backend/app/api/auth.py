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
    user = json.loads(params.get("user", "{}"))
    if user.get("id") != settings.teacher_telegram_id:
        raise HTTPException(403, "Not authorized")
    token = jwt.encode(
        {"sub": str(user["id"]), "exp": int(time.time()) + 1800},
        settings.jwt_secret, algorithm="HS256",
    )
    return {"access_token": token}
