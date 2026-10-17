from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.auth import (
    check_password_policy,
    client_ip,
    hash_password,
    new_session,
    normalize_email,
    normalize_name,
    public_user,
    read_platform_session,
    require_anon_csrf,
    require_csrf,
    require_user,
    set_cookie,
    verify_password,
)
from app.deps import platform_db
from app.models import AuditLog, PlatformSession, PlatformUser
from app.util import new_id, utcnow

router = APIRouter()


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str
    name: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


@router.get("/auth/csrf")
def issue_csrf(response: Response, request: Request):
    token = secrets.token_urlsafe(32)
    set_cookie(response, request.app.state.settings, "awp_csrf", token, True)
    return {"csrfToken": token}


@router.post("/auth/register")
def register(payload: RegisterIn, request: Request, response: Response, db=Depends(platform_db)):
    require_anon_csrf(request)
    _limit(request, f"register:{client_ip(request)}", 5, 600)
    email = normalize_email(payload.email)
    name = normalize_name(payload.name)
    check_password_policy(payload.password)
    if db.scalar(select(PlatformUser).where(PlatformUser.email == email)):
        raise HTTPException(status_code=409, detail="这个邮箱已经注册过了")
    user = PlatformUser(
        id=new_id(),
        email=email,
        name=name,
        password_hash=hash_password(payload.password, request.app.state.settings.bcrypt_rounds),
        role="user",
        status="active",
        user_group="default",
        quota=20,
        used_quota=0,
        created_at=utcnow(),
    )
    db.add(user)
    session = _login_session(db, user)
    _audit(db, request, user.id, "REGISTER")
    return _auth_response(response, request, user, session)


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db=Depends(platform_db)):
    require_anon_csrf(request)
    _limit(request, f"login:{client_ip(request)}", 10, 300)
    email = normalize_email(payload.email)
    check_password_policy(payload.password)
    user = db.scalar(select(PlatformUser).where(PlatformUser.email == email, PlatformUser.deleted_at.is_(None)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="账号已停用")
    session = _login_session(db, user)
    _audit(db, request, user.id, "LOGIN")
    return _auth_response(response, request, user, session)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    db.delete(session)
    response.delete_cookie("awp_session", path="/")
    _audit(db, request, user.id, "LOGOUT")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, db=Depends(platform_db)):
    found = read_platform_session(request, db)
    if found is None:
        raise HTTPException(status_code=401, detail="请先登录")
    user, session = found
    return {"user": public_user(user, request.app.state.settings), "csrfToken": session.csrf_token}


def _login_session(db, user: PlatformUser) -> PlatformSession:
    for old in db.scalars(select(PlatformSession).where(PlatformSession.user_id == user.id)).all():
        db.delete(old)
    session = new_session(user.id)
    db.add(session)
    return session


def _auth_response(response: Response, request: Request, user: PlatformUser, session: PlatformSession) -> dict:
    set_cookie(response, request.app.state.settings, "awp_session", session.id, True)
    return {"user": public_user(user, request.app.state.settings), "csrfToken": session.csrf_token}


def _audit(db, request: Request, user_id: str, action: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            user_id=user_id,
            ip=client_ip(request)[:64],
            action=action,
            detail="",
            created_at=utcnow(),
        )
    )


def _limit(request: Request, key: str, limit: int, window: int) -> None:
    if not request.app.state.limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")
