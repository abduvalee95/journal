from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.auth import decode_token
from app.config import settings

_bearer = HTTPBearer(auto_error=False)


async def require_teacher(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    """Guard every /api/* route: a valid session token belonging to the teacher.

    The subject is compared against TEACHER_TELEGRAM_ID here rather than being
    left to the issuer. auth.py is the only issuer today, but that makes the
    guarantee a property of two files agreeing; checking it at the guard makes
    it local and true regardless of what else ever mints a token.
    """
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(401, "Invalid token")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token")
    if user_id != settings.teacher_telegram_id:
        raise HTTPException(403, "Not authorized")
    return user_id
