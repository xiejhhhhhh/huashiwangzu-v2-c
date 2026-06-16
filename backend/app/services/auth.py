import logging
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
from jose import jwt, JWTError
from app.config import get_settings
from app.models.user import User
from app.core.exceptions import AuthError, RateLimitError

logger = logging.getLogger("v2.auth")
settings = get_settings()

# In-memory rate limiting (login attempts per username)
_login_attempts: dict[str, list[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as e:
        logger.error(f"bcrypt verify error: {e}")
        return False


def create_access_token(user_id: int, role: str, session_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "sv": session_version, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise AuthError("Invalid or expired token")


def check_login_rate_limit(username: str):
    now = time.time()
    attempts = _login_attempts.get(username, [])
    attempts = [t for t in attempts if now - t < LOGIN_LOCKOUT_MINUTES * 60]
    _login_attempts[username] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise RateLimitError("Too many login attempts, please try again later")


def record_login_attempt(username: str, success: bool):
    if not success:
        now = time.time()
        _login_attempts.setdefault(username, []).append(now)


def clear_login_rate_limit(username: str):
    _login_attempts.pop(username, None)


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    check_login_rate_limit(username)
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        record_login_attempt(username, False)
        raise AuthError("Invalid username or password")
    if not user.enabled:
        raise AuthError("Account is disabled")
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_system_log(db: AsyncSession, level: str, module: str, action: str, message: str, user_id: int = 0):
    from app.models.system import SystemLog
    log = SystemLog(level=level, module=module, action=action, message=message, user_id=user_id)
    db.add(log)
    await db.commit()
