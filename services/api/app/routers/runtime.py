from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.access import can_view_app, is_owner, schema_of
from app.auth import (
    check_password_policy,
    client_ip,
    hash_password,
    normalize_email,
    normalize_name,
    read_platform_session,
    require_anon_csrf,
    set_cookie,
    verify_password,
)
from app.deps import apps_db, platform_db
from app.models import AppSession, Application, AppUser, AppVersion
from app.runtime.service import (
    create_record,
    delete_record,
    file_readable,
    get_record,
    list_records,
    open_file,
    save_upload,
    update_record,
)
from app.util import as_utc, is_uuid, new_id, utcnow

router = APIRouter()


class AppRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str
    name: str


class AppLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


@router.get("/runtime/{app_id}/auth/csrf")
def app_csrf(app_id: str, request: Request, response: Response, platform=Depends(platform_db)):
    _resolve(request, platform, app_id, False)
    token = secrets.token_urlsafe(32)
    set_cookie(response, request.app.state.settings, "awp_app_csrf", token, True, _cookie_path(app_id))
    return {"csrfToken": token}


@router.post("/runtime/{app_id}/auth/register")
def app_register(app_id: str, payload: AppRegisterIn, request: Request, response: Response, platform=Depends(platform_db), apps=Depends(apps_db)):
    _resolve(request, platform, app_id, False)
    _anon_csrf(request)
    _limit(request, f"app-register:{client_ip(request)}", 5, 600)
    email = normalize_email(payload.email)
    name = normalize_name(payload.name)
    check_password_policy(payload.password)
    if apps.scalar(select(AppUser).where(AppUser.app_id == app_id, AppUser.email == email)):
        raise HTTPException(status_code=409, detail="这个邮箱已经注册过了")
    user = AppUser(
        id=new_id(),
        app_id=app_id,
        email=email,
        name=name,
        password_hash=hash_password(payload.password, request.app.state.settings.bcrypt_rounds),
        role="user",
        created_at=utcnow(),
    )
    apps.add(user)
    session = _new_app_session(apps, user)
    return _app_auth(response, request, user, session)


@router.post("/runtime/{app_id}/auth/login")
def app_login(app_id: str, payload: AppLoginIn, request: Request, response: Response, platform=Depends(platform_db), apps=Depends(apps_db)):
    _resolve(request, platform, app_id, False)
    _anon_csrf(request)
    _limit(request, f"app-login:{client_ip(request)}", 10, 300)
    email = normalize_email(payload.email)
    check_password_policy(payload.password)
    user = apps.scalar(select(AppUser).where(AppUser.app_id == app_id, AppUser.email == email))
    if user is None or user.role not in {"user", "editor", "admin", "owner"} or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    session = _new_app_session(apps, user)
    return _app_auth(response, request, user, session)


@router.post("/runtime/{app_id}/auth/logout")
def app_logout(app_id: str, request: Request, response: Response, platform=Depends(platform_db), apps=Depends(apps_db)):
    _resolve(request, platform, app_id, False)
    found = _read_app_user(request, apps, app_id)
    if found is None:
        raise HTTPException(status_code=401, detail="请先登录")
    _user, session = found
    _csrf(request, session.csrf_token)
    apps.delete(session)
    response.delete_cookie("awp_app_session", path=_cookie_path(app_id))
    return {"ok": True}


@router.get("/runtime/{app_id}/auth/me")
def app_me(app_id: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _resolve(request, platform, app_id, False)
    found = _read_app_user(request, apps, app_id)
    if found is None:
        raise HTTPException(status_code=401, detail="请先登录")
    user, session = found
    return {"user": _public_app_user(user), "csrfToken": session.csrf_token}


@router.get("/runtime/{app_id}/entities/{entity}")
def list_entity(app_id: str, entity: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, _draft(request))
    found = _read_app_user(request, apps, app_id)
    filters = {key[2:]: value for key, value in request.query_params.multi_items() if key.startswith("f_") and value}
    return list_records(
        apps,
        schema,
        app_id,
        entity,
        found[0] if found else None,
        request.query_params.get("q", ""),
        filters,
        _number(request.query_params.get("page"), 1, 1, 1000),
        _number(request.query_params.get("pageSize"), 12, 1, 24),
    )


@router.post("/runtime/{app_id}/entities/{entity}")
async def post_entity(app_id: str, entity: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, _draft(request))
    user, session = _require_app_user(request, apps, app_id)
    _csrf(request, session.csrf_token)
    _limit(request, f"write:{app_id}:{user.id}", 30, 60)
    payload = await request.json()
    return create_record(apps, schema, app_id, entity, user, payload)


@router.get("/runtime/{app_id}/entities/{entity}/{record_id}")
def read_entity(app_id: str, entity: str, record_id: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, _draft(request))
    found = _read_app_user(request, apps, app_id)
    return get_record(apps, schema, app_id, entity, record_id, found[0] if found else None)


@router.patch("/runtime/{app_id}/entities/{entity}/{record_id}")
async def patch_entity(app_id: str, entity: str, record_id: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, _draft(request))
    user, session = _require_app_user(request, apps, app_id)
    _csrf(request, session.csrf_token)
    _limit(request, f"write:{app_id}:{user.id}", 30, 60)
    return update_record(apps, schema, app_id, entity, record_id, user, await request.json())


@router.delete("/runtime/{app_id}/entities/{entity}/{record_id}")
def remove_entity(app_id: str, entity: str, record_id: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, _draft(request))
    user, session = _require_app_user(request, apps, app_id)
    _csrf(request, session.csrf_token)
    _limit(request, f"write:{app_id}:{user.id}", 30, 60)
    delete_record(apps, schema, app_id, entity, record_id, user)
    return {"ok": True}


@router.post("/runtime/{app_id}/upload")
async def upload(app_id: str, request: Request, file: UploadFile = File(...), platform=Depends(platform_db), apps=Depends(apps_db)):
    _resolve(request, platform, app_id, _draft(request))
    user, session = _require_app_user(request, apps, app_id)
    _csrf(request, session.csrf_token)
    _limit(request, f"upload:{user.id}", 20, 60)
    blob = await _read_limited(file)
    return save_upload(apps, request.app.state.settings, app_id, user, blob)


@router.get("/runtime/{app_id}/files/{file_id}")
def download(app_id: str, file_id: str, request: Request, platform=Depends(platform_db), apps=Depends(apps_db)):
    _app, schema, _owner = _resolve(request, platform, app_id, False)
    stored, path = open_file(apps, request.app.state.settings, app_id, file_id)
    found = _read_app_user(request, apps, app_id)
    if not file_readable(apps, schema, app_id, stored, found[0] if found else None):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path,
        media_type=stored.mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{stored.id}{stored.ext}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


def _resolve(request: Request, platform, app_id: str, draft: bool):
    if not is_uuid(app_id):
        raise HTTPException(status_code=404, detail="网站不存在")
    app = platform.get(Application, app_id)
    found = read_platform_session(request, platform)
    user = found[0] if found else None
    if app is None or not can_view_app(user, app):
        raise HTTPException(status_code=404, detail="网站不存在")
    if app.current_version_id is None:
        raise HTTPException(status_code=409, detail="网站还在生成")
    owner = is_owner(user, app)
    if owner and (draft or app.published_version_id is None):
        version_id = app.current_version_id
    elif app.published_version_id:
        version_id = app.published_version_id
    else:
        raise HTTPException(status_code=404, detail="网站不存在")
    version = platform.get(AppVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="网站不存在")
    return app, schema_of(version), owner


def _draft(request: Request) -> bool:
    return request.query_params.get("draft") in {"1", "true"}


def _read_app_user(request: Request, apps, app_id: str):
    sid = request.cookies.get("awp_app_session")
    if not sid:
        return None
    session = apps.get(AppSession, sid)
    expires = as_utc(session.expires_at) if session else None
    if session is None or session.app_id != app_id or expires is None or expires < utcnow():
        return None
    user = apps.get(AppUser, session.app_user_id)
    if user is None or user.app_id != app_id:
        return None
    return user, session


def _require_app_user(request: Request, apps, app_id: str):
    found = _read_app_user(request, apps, app_id)
    if found is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return found


def _new_app_session(apps, user: AppUser) -> AppSession:
    for old in apps.scalars(select(AppSession).where(AppSession.app_user_id == user.id)).all():
        apps.delete(old)
    session = AppSession(
        id=secrets.token_urlsafe(32),
        app_user_id=user.id,
        app_id=user.app_id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(days=7),
        created_at=utcnow(),
    )
    apps.add(session)
    return session


def _cookie_path(app_id: str) -> str:
    return f"/api/v1/runtime/{app_id}"


def _app_auth(response: Response, request: Request, user: AppUser, session: AppSession) -> dict:
    set_cookie(response, request.app.state.settings, "awp_app_session", session.id, True, _cookie_path(user.app_id))
    return {"user": _public_app_user(user), "csrfToken": session.csrf_token}


def _public_app_user(user: AppUser) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role}


def _anon_csrf(request: Request) -> None:
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("awp_app_csrf", "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def _csrf(request: Request, expected: str) -> None:
    header = request.headers.get("x-csrf-token", "")
    if not header or not secrets.compare_digest(header, expected):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def _limit(request: Request, key: str, limit: int, window: int) -> None:
    if not request.app.state.limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")


def _number(value: str | None, default: int, low: int, high: int) -> int:
    try:
        number = int(value) if value is not None else default
    except ValueError:
        return default
    return min(max(number, low), high)


async def _read_limited(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="图片不能超过 5MB")
        chunks.append(chunk)
    return b"".join(chunks)
