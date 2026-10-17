from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from collections import defaultdict
from datetime import timedelta

import bcrypt
from fastapi import HTTPException, Request

from app.models import PlatformSession, PlatformUser
from app.settings import Settings
from app.util import as_utc, new_id, utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        with self._lock:
            recent = [stamp for stamp in self._hits[key] if now - stamp < window]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


def hash_password(password: str, rounds: int) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_password_policy(password: str) -> None:
    size = len(password.encode())
    if size < 8 or size > 72:
        raise HTTPException(status_code=400, detail="密码需要 8 到 72 个字节")


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_RE.match(normalized) or len(normalized) > 254:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return normalized


def normalize_name(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch >= " " and ch != "\x7f")
    if not cleaned or len(cleaned) > 40:
        raise HTTPException(status_code=400, detail="名字需要 1 到 40 个字符")
    return cleaned


def client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def new_session(user_id: str) -> PlatformSession:
    return PlatformSession(
        id=secrets.token_urlsafe(32),
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(days=7),
        created_at=utcnow(),
    )


def read_platform_session(request: Request, db) -> tuple[PlatformUser, PlatformSession] | None:
    sid = request.cookies.get("awp_session")
    if not sid:
        return None
    session = db.get(PlatformSession, sid)
    expires = as_utc(session.expires_at) if session else None
    if session is None or expires is None or expires < utcnow():
        return None
    user = db.get(PlatformUser, session.user_id)
    if user is None or user.deleted_at is not None or user.status != "active":
        return None
    return user, session


def require_user(request: Request, db) -> tuple[PlatformUser, PlatformSession]:
    found = read_platform_session(request, db)
    if found is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return found


def require_csrf(request: Request, session: PlatformSession) -> None:
    header = request.headers.get("x-csrf-token", "")
    if not header or not secrets.compare_digest(header, session.csrf_token):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def require_anon_csrf(request: Request) -> None:
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("awp_csrf", "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def set_cookie(response, settings: Settings, key: str, value: str, http_only: bool, path: str = "/") -> None:
    response.set_cookie(
        key,
        value,
        httponly=http_only,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path=path,
    )


def account_role(user: PlatformUser, settings: Settings) -> str:
    if user.email in settings.admin_emails:
        return "root"
    if user.role in {"user", "admin", "root"}:
        return user.role
    return "user"


def is_operator(user: PlatformUser, settings: Settings) -> bool:
    return account_role(user, settings) in {"admin", "root"}


def public_user(user: PlatformUser, settings: Settings) -> dict:
    role = account_role(user, settings)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "admin": role in {"admin", "root"},
        "role": role,
        "status": user.status,
        "group": user.user_group,
        "quota": user.quota,
        "usedQuota": user.used_quota,
    }


def fresh_id() -> str:
    return new_id()
