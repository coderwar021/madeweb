from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import account_role, client_ip, is_operator, normalize_name, public_user, require_csrf, require_user
from app.deps import platform_db
from app.models import AuditLog, PlatformSession, PlatformUser
from app.util import is_uuid, new_id, utcnow

router = APIRouter()

GROUP_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RANK = {"user": 1, "admin": 10, "root": 100}


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    group: str | None = None
    quota: int | None = Field(default=None, ge=0, le=1_000_000)
    role: Literal["user", "admin"] | None = None
    status: Literal["active", "disabled"] | None = None


class ManageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable", "disable", "delete", "promote", "demote"]


@router.get("/users")
def list_users(request: Request, q: str = "", db=Depends(platform_db)):
    actor, _session = require_user(request, db)
    _require_staff(request, actor)
    _limit(request, f"users:{actor.id}", 30, 60)
    needle = q.strip().lower()[:80]
    rows = db.scalars(select(PlatformUser).where(PlatformUser.deleted_at.is_(None)).order_by(PlatformUser.created_at.desc())).all()
    if needle:
        rows = [user for user in rows if needle in user.email or needle in user.name.lower()]
    settings = request.app.state.settings
    return {"users": [public_user(user, settings) for user in rows[:100]]}


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, request: Request, db=Depends(platform_db)):
    actor, session = require_user(request, db)
    require_csrf(request, session)
    _require_staff(request, actor)
    _limit(request, f"users:{actor.id}", 30, 60)
    target = _target(db, user_id)
    _guard(actor, target, request.app.state.settings)
    settings = request.app.state.settings
    if payload.name is not None:
        target.name = normalize_name(payload.name)
    if payload.group is not None:
        if GROUP_RE.fullmatch(payload.group) is None:
            raise HTTPException(status_code=400, detail="分组格式不正确")
        target.user_group = payload.group
    if payload.quota is not None:
        target.quota = payload.quota
    if payload.role is not None:
        _set_role(actor, target, payload.role, settings)
    if payload.status is not None:
        target.status = payload.status
        if payload.status == "disabled":
            _drop_sessions(db, target.id)
    _audit(db, request, actor.id, "USER_UPDATE", target.id)
    db.commit()
    return {"user": public_user(target, settings)}


@router.post("/users/{user_id}/manage")
def manage_user(user_id: str, payload: ManageIn, request: Request, db=Depends(platform_db)):
    actor, session = require_user(request, db)
    require_csrf(request, session)
    _require_staff(request, actor)
    _limit(request, f"users:{actor.id}", 30, 60)
    target = _target(db, user_id)
    settings = request.app.state.settings
    _guard(actor, target, settings)
    if payload.action == "enable":
        target.status = "active"
    elif payload.action == "disable":
        target.status = "disabled"
        _drop_sessions(db, target.id)
    elif payload.action == "delete":
        target.deleted_at = utcnow()
        target.status = "disabled"
        _drop_sessions(db, target.id)
    elif payload.action == "promote":
        _set_role(actor, target, "admin", settings)
    elif payload.action == "demote":
        _set_role(actor, target, "user", settings)
    _audit(db, request, actor.id, f"USER_{payload.action.upper()}", target.id)
    db.commit()
    return {"user": public_user(target, settings)}


def _require_staff(request: Request, user: PlatformUser) -> None:
    if not is_operator(user, request.app.state.settings):
        raise HTTPException(status_code=403, detail="没有用户管理权限")


def _target(db, user_id: str) -> PlatformUser:
    if not is_uuid(user_id):
        raise HTTPException(status_code=404, detail="用户不存在")
    user = db.get(PlatformUser, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _guard(actor: PlatformUser, target: PlatformUser, settings) -> None:
    if target.id == actor.id or RANK[account_role(target, settings)] >= RANK[account_role(actor, settings)]:
        raise HTTPException(status_code=403, detail="不能管理这个账号")


def _set_role(actor: PlatformUser, target: PlatformUser, role: str, settings) -> None:
    if account_role(actor, settings) != "root":
        raise HTTPException(status_code=403, detail="只有根管理员可以调整管理员")
    current = account_role(target, settings)
    if role == "admin" and current != "user":
        raise HTTPException(status_code=400, detail="这个账号已经是管理员")
    if role == "user" and current != "admin":
        raise HTTPException(status_code=400, detail="这个账号不是管理员")
    target.role = role


def _drop_sessions(db, user_id: str) -> None:
    for session in db.scalars(select(PlatformSession).where(PlatformSession.user_id == user_id)).all():
        db.delete(session)


def _audit(db, request: Request, user_id: str, action: str, target_id: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            user_id=user_id,
            ip=client_ip(request)[:64],
            action=action[:40],
            detail=target_id,
            created_at=utcnow(),
        )
    )


def _limit(request: Request, key: str, limit: int, window: int) -> None:
    if not request.app.state.limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")
