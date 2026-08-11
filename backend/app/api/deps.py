from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

_bearer = HTTPBearer()

async def require_teacher(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
