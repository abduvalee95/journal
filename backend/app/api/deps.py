from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

_bearer = HTTPBearer(auto_error=False)

async def require_teacher(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(401, "Invalid token")
    try:
        return int(sub)
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token")
