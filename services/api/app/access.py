from __future__ import annotations

from fastapi import HTTPException

from app.models import Application, PlatformUser
from app.util import loads


def is_owner(user: PlatformUser | None, app: Application) -> bool:
    return user is not None and user.deleted_at is None and app.owner_id == user.id


def can_view_app(user: PlatformUser | None, app: Application) -> bool:
    if app.deleted_at is not None:
        return False
    if app.status == "disabled" and not is_owner(user, app):
        return False
    if is_owner(user, app):
        return True
    if app.visibility == "private" or app.status != "active":
        return False
    return app.visibility in {"public", "unlisted"} and app.published_version_id is not None


def require_owner(user: PlatformUser, app: Application) -> None:
    if not is_owner(user, app) or app.deleted_at is not None:
        raise HTTPException(status_code=404, detail="网站不存在")


def schema_of(version) -> dict:
    data = loads(version.schema_json)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="internal error")
    return data
