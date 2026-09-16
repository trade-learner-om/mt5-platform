from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from .db import get_db, parse_object_id
from .platform_users import resolve_user_for_session_async


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()
PLATFORM_JWT_AUDIENCE = "platform"


def decode_platform_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=PLATFORM_JWT_AUDIENCE,
    )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def new_session_id() -> str:
    return uuid4().hex


def create_access_token(user_id: str, session_id: str) -> str:
    app_tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(app_tz)
    next_cutoff = datetime.combine(now_local.date(), time(hour=23, minute=10), tzinfo=app_tz)
    if now_local >= next_cutoff:
        next_cutoff = next_cutoff + timedelta(days=1)

    expire = int(next_cutoff.astimezone(timezone.utc).timestamp())
    payload = {"sub": str(user_id), "sid": session_id, "exp": expire, "aud": PLATFORM_JWT_AUDIENCE}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def is_session_active(user: dict, session_id: str) -> bool:
    sid = str(session_id or "")
    if not sid:
        return False
    if str(user.get("current_session_id") or "") == sid:
        return True
    active_session_ids = user.get("active_session_ids")
    if isinstance(active_session_ids, list):
        return sid in {str(item) for item in active_session_ids if item}
    return False


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    token = credentials.credentials
    try:
        payload = decode_platform_token(token)
        user_id = parse_object_id(payload["sub"])
        session_id = str(payload.get("sid") or "")
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await resolve_user_for_session_async(db, user_id, session_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not is_session_active(user, session_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if user.get("is_active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return user


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
