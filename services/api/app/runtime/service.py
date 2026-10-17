from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import select

from app.db import file_path
from app.models import AppUser, Record, StoredFile
from app.settings import Settings
from app.util import dumps, is_uuid, loads, new_id, utcnow
from awp_security.uploads import sniff_image

DECIMAL_RE = re.compile(r"^\d{1,12}(\.\d{1,2})?$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")
RANK = {"all": 3, "participant": 2, "own": 1}


def entity_by_name(schema: dict, name: str) -> dict | None:
    for entity in schema.get("entities", []):
        if entity["name"] == name:
            return entity
    return None


def permission_scope(schema: dict, role: str, action: str, resource: str) -> str | None:
    if role in {"owner", "admin"}:
        return "all"
    found: list[str] = []
    for perm in schema.get("permissions", []):
        if perm.get("role") == role and perm.get("action") == action and perm.get("resource") == resource:
            found.append(perm.get("scope", "all"))
    if not found:
        return None
    return max(found, key=lambda item: RANK[item])


def list_records(apps, schema: dict, app_id: str, entity_name: str, user: AppUser | None, q: str, filters: dict, page: int, page_size: int) -> dict:
    entity = _require_entity(schema, entity_name)
    scope = permission_scope(schema, user.role if user else "guest", "view", entity_name)
    if scope is None:
        raise HTTPException(status_code=403, detail="没有查看权限")
    rows = apps.scalars(
        select(Record)
        .where(Record.app_id == app_id, Record.entity == entity_name, Record.deleted_at.is_(None))
        .order_by(Record.created_at.desc())
        .limit(300)
    ).all()
    visible = [row for row in rows if _visible(row, entity, scope, user)]
    if q:
        needle = q.strip().lower()[:80]
        visible = [row for row in visible if _matches(row, entity, needle)]
    for key, value in filters.items():
        if key not in entity["fields"] or len(value) > 80:
            raise HTTPException(status_code=400, detail="筛选条件无效")
        visible = [row for row in visible if str(loads(row.data).get(key) or "") == value]
    total = len(visible)
    start = (page - 1) * page_size
    chosen = visible[start : start + page_size]
    return {"items": present_many(apps, schema, entity, chosen), "page": page, "pageSize": page_size, "total": total}


def create_record(apps, schema: dict, app_id: str, entity_name: str, user: AppUser | None, payload: dict) -> dict:
    entity = _require_entity(schema, entity_name)
    scope = permission_scope(schema, user.role if user else "guest", "create", entity_name)
    if scope is None or user is None:
        raise HTTPException(status_code=403, detail="没有创建权限")
    data = coerce(apps, app_id, entity, payload, user, None, schema)
    if _duplicate(apps, app_id, entity, data, None):
        raise HTTPException(status_code=409, detail="已经存在")
    now = utcnow()
    record = Record(
        id=new_id(),
        app_id=app_id,
        entity=entity_name,
        data=dumps(data),
        owner_id=user.id,
        created_at=now,
        updated_at=now,
    )
    apps.add(record)
    apps.flush()
    return present_many(apps, schema, entity, [record])[0]


def get_record(apps, schema: dict, app_id: str, entity_name: str, record_id: str, user: AppUser | None) -> dict:
    entity = _require_entity(schema, entity_name)
    record = _owned_record(apps, app_id, entity_name, record_id)
    scope = permission_scope(schema, user.role if user else "guest", "view", entity_name)
    if scope is None or not _visible(record, entity, scope, user):
        raise HTTPException(status_code=404, detail="内容不存在")
    return present_many(apps, schema, entity, [record])[0]


def update_record(apps, schema: dict, app_id: str, entity_name: str, record_id: str, user: AppUser | None, payload: dict) -> dict:
    entity = _require_entity(schema, entity_name)
    record = _owned_record(apps, app_id, entity_name, record_id)
    role = user.role if user else "guest"
    scope = permission_scope(schema, role, "update", entity_name)
    if user is None or scope is None or not _visible(record, entity, scope, user):
        raise HTTPException(status_code=403, detail="没有修改权限")
    data = coerce(apps, app_id, entity, payload, user, loads(record.data), schema)
    if _duplicate(apps, app_id, entity, data, record.id):
        raise HTTPException(status_code=409, detail="已经存在")
    record.data = dumps(data)
    record.updated_at = utcnow()
    return present_many(apps, schema, entity, [record])[0]


def delete_record(apps, schema: dict, app_id: str, entity_name: str, record_id: str, user: AppUser | None) -> None:
    entity = _require_entity(schema, entity_name)
    record = _owned_record(apps, app_id, entity_name, record_id)
    role = user.role if user else "guest"
    scope = permission_scope(schema, role, "delete", entity_name)
    if user is None or scope is None or not _visible(record, entity, scope, user):
        raise HTTPException(status_code=403, detail="没有删除权限")
    record.deleted_at = utcnow()


def save_upload(apps, settings: Settings, app_id: str, user: AppUser, blob: bytes) -> dict:
    sniffed = sniff_image(blob)
    if sniffed is None:
        raise HTTPException(status_code=400, detail="只接受 JPG、PNG、GIF 或 WebP")
    mime, ext = sniffed
    file_id = new_id()
    path = file_path(settings, app_id, file_id, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    apps.add(
        StoredFile(
            id=file_id,
            app_id=app_id,
            owner_id=user.id,
            ext=ext,
            mime=mime,
            size=len(blob),
            created_at=utcnow(),
        )
    )
    return {"id": file_id, "url": f"/api/v1/runtime/{app_id}/files/{file_id}", "mime": mime}


def file_readable(apps, schema: dict, app_id: str, stored: StoredFile, user: AppUser | None) -> bool:
    if user is not None and stored.owner_id == user.id:
        return True
    rows = apps.scalars(
        select(Record).where(Record.app_id == app_id, Record.deleted_at.is_(None)).limit(500)
    ).all()
    for row in rows:
        entity = entity_by_name(schema, row.entity)
        data = loads(row.data) or {}
        if entity is None or not _references_file(data, entity, stored.id):
            continue
        scope = permission_scope(schema, user.role if user else "guest", "view", row.entity)
        if scope and _visible(row, entity, scope, user):
            return True
    return False


def open_file(apps, settings: Settings, app_id: str, file_id: str) -> tuple[StoredFile, object]:
    if not is_uuid(file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    stored = apps.get(StoredFile, file_id)
    if stored is None or stored.app_id != app_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = file_path(settings, app_id, stored.id, stored.ext)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return stored, path


def coerce(apps, app_id: str, entity: dict, payload: dict, user: AppUser, existing: dict | None, schema: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="内容格式不正确")
    data: dict = {}
    existing = existing or {}
    for name, spec in entity["fields"].items():
        if spec.get("auto") == "current":
            data[name] = existing.get(name) or user.id
            continue
        if _state_locked(entity, spec):
            data[name] = _locked_state(spec, payload, existing, name)
            continue
        present = name in payload
        raw = payload.get(name)
        if isinstance(raw, str):
            raw = raw.replace("\x00", "").strip()
        missing = not present or raw in (None, "")
        if missing:
            if "default" in spec and not existing:
                data[name] = spec["default"]
            elif name in existing:
                data[name] = existing.get(name)
            elif spec.get("required"):
                raise HTTPException(status_code=400, detail=f"{spec['label']}为必填")
            else:
                data[name] = [] if spec["type"] == "file[]" else None
            continue
        data[name] = _convert(apps, app_id, spec, raw, user, existing.get(name), schema)
    return data


def present_many(apps, schema: dict, entity: dict, records: list[Record]) -> list[dict]:
    raw = [(record, loads(record.data) or {}) for record in records]
    user_ids: set[str] = set()
    relation_ids: set[str] = set()
    for _record, data in raw:
        for name, spec in entity["fields"].items():
            value = data.get(name)
            if spec["type"] == "user" and isinstance(value, str):
                user_ids.add(value)
            if spec["type"] == "relation" and isinstance(value, str):
                relation_ids.add(value)
    users = {}
    if user_ids:
        rows = apps.scalars(select(AppUser).where(AppUser.id.in_(user_ids))).all()
        users = {row.id: row for row in rows if row.app_id == records[0].app_id} if records else {}
    related = {}
    if relation_ids:
        rows = apps.scalars(select(Record).where(Record.id.in_(relation_ids), Record.deleted_at.is_(None))).all()
        for row in rows:
            if records and row.app_id != records[0].app_id:
                continue
            target = entity_by_name(schema, row.entity)
            if target and target.get("access") == "public":
                related[row.id] = _summary(row, target)
            else:
                related[row.id] = {"id": row.id}
    presented = []
    for record, data in raw:
        out = {}
        for name, spec in entity["fields"].items():
            value = data.get(name)
            if spec["type"] == "user":
                person = users.get(value)
                out[name] = {"id": value, "name": person.name} if person else None
            elif spec["type"] == "relation" and isinstance(value, str):
                out[name] = related.get(value) or {"id": value}
            else:
                out[name] = value
        presented.append({"id": record.id, "data": out, "createdAt": record.created_at.isoformat()})
    return presented


def _summary(record: Record, entity: dict) -> dict:
    data = loads(record.data) or {}
    title = data.get(entity["titleField"])
    image = None
    for name, spec in entity["fields"].items():
        if spec["type"] == "file[]" and isinstance(data.get(name), list) and data[name]:
            image = data[name][0]
            break
        if spec["type"] == "file" and isinstance(data.get(name), str):
            image = data[name]
            break
    summary = {"id": record.id, "title": title if isinstance(title, str) else None, "image": image}
    if "price" in entity["fields"]:
        summary["price"] = data.get("price")
    return summary


def _require_entity(schema: dict, name: str) -> dict:
    entity = entity_by_name(schema, name)
    if entity is None or not re.fullmatch(r"[A-Z][A-Za-z0-9]{0,32}", name):
        raise HTTPException(status_code=404, detail="内容类型不存在")
    return entity


def _owned_record(apps, app_id: str, entity_name: str, record_id: str) -> Record:
    if not is_uuid(record_id):
        raise HTTPException(status_code=404, detail="内容不存在")
    record = apps.get(Record, record_id)
    if record is None or record.app_id != app_id or record.entity != entity_name or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="内容不存在")
    return record


def _visible(record: Record, entity: dict, scope: str, user: AppUser | None) -> bool:
    if scope == "all":
        return True
    if user is None:
        return False
    if scope == "own":
        return record.owner_id == user.id
    if scope == "participant":
        if record.owner_id == user.id:
            return True
        data = loads(record.data) or {}
        return any(data.get(name) == user.id for name, spec in entity["fields"].items() if spec.get("participant"))
    return False


def _matches(record: Record, entity: dict, needle: str) -> bool:
    data = loads(record.data) or {}
    for name, spec in entity["fields"].items():
        if spec["type"] in {"string", "text"} and needle in str(data.get(name) or "").lower():
            return True
    return False


def _duplicate(apps, app_id: str, entity: dict, data: dict, exclude_id: str | None) -> bool:
    fields = entity.get("unique") or []
    if not fields:
        return False
    rows = apps.scalars(
        select(Record).where(Record.app_id == app_id, Record.entity == entity["name"], Record.deleted_at.is_(None)).limit(500)
    ).all()
    for row in rows:
        if row.id == exclude_id:
            continue
        current = loads(row.data) or {}
        if all(current.get(field) == data.get(field) for field in fields):
            return True
    return False


def _state_locked(entity: dict, spec: dict) -> bool:
    return entity.get("access") != "public" and spec.get("type") == "enum" and "default" in spec


def _locked_state(spec: dict, payload: dict, existing: dict, name: str):
    current = existing.get(name) if name in existing and existing.get(name) not in (None, "") else spec["default"]
    if name not in payload or payload.get(name) in (None, ""):
        return current
    requested = payload.get(name)
    allowed = {spec["default"], current, "cancelled"}
    if requested not in spec.get("values", []) or requested not in allowed:
        raise HTTPException(status_code=400, detail="状态不能这样修改")
    return requested


def _references_file(data: dict, entity: dict, file_id: str) -> bool:
    for name, spec in entity["fields"].items():
        value = data.get(name)
        if spec.get("type") == "file" and value == file_id:
            return True
        if spec.get("type") == "file[]" and isinstance(value, list) and file_id in value:
            return True
    return False


def _convert(apps, app_id: str, spec: dict, value, user: AppUser, existing, schema: dict):
    kind = spec["type"]
    if kind == "string":
        return _text_value(value, 200)
    if kind == "text":
        return _text_value(value, 5000)
    if kind == "decimal":
        if isinstance(value, bool):
            raise HTTPException(status_code=400, detail=f"{spec['label']}格式不正确")
        if isinstance(value, int):
            value = str(value)
        if isinstance(value, str):
            value = value.strip()
        if not isinstance(value, str) or not DECIMAL_RE.match(value):
            raise HTTPException(status_code=400, detail=f"{spec['label']}格式不正确")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
            raise HTTPException(status_code=400, detail=f"{spec['label']}格式不正确")
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise HTTPException(status_code=400, detail=f"{spec['label']}格式不正确")
        return value
    if kind == "enum":
        if value not in spec.get("values", []):
            raise HTTPException(status_code=400, detail=f"{spec['label']}不在可选范围内")
        return value
    if kind == "datetime":
        if not isinstance(value, str) or not DATETIME_RE.match(value):
            raise HTTPException(status_code=400, detail=f"{spec['label']}格式不正确")
        return value
    if kind == "user":
        if not isinstance(value, str) or not is_uuid(value):
            raise HTTPException(status_code=400, detail=f"{spec['label']}不存在")
        person = apps.get(AppUser, value)
        if person is None or person.app_id != app_id:
            raise HTTPException(status_code=400, detail=f"{spec['label']}不存在")
        return value
    if kind == "relation":
        if not isinstance(value, str) or not is_uuid(value):
            raise HTTPException(status_code=400, detail=f"{spec['label']}不存在")
        target = apps.get(Record, value)
        if target is None or target.app_id != app_id or target.entity != spec["target"] or target.deleted_at is not None:
            raise HTTPException(status_code=400, detail=f"{spec['label']}不存在")
        target_entity = entity_by_name(schema, spec["target"])
        scope = permission_scope(schema, user.role, "view", spec["target"])
        if target_entity is None or scope is None or not _visible(target, target_entity, scope, user):
            raise HTTPException(status_code=400, detail=f"{spec['label']}不存在")
        return value
    if kind == "file":
        return _file_id(apps, app_id, value, user, existing if isinstance(existing, str) else None)
    if kind == "file[]":
        if not isinstance(value, list) or len(value) > 6:
            raise HTTPException(status_code=400, detail="图片最多 6 张")
        existing_ids = set(existing) if isinstance(existing, list) else set()
        return [_file_id(apps, app_id, item, user, item if item in existing_ids else None) for item in value]
    raise HTTPException(status_code=400, detail="字段类型无效")


def _text_value(value, limit: int) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="文本格式不正确")
    cleaned = value.replace("\x00", "").strip()
    if len(cleaned) > limit:
        raise HTTPException(status_code=400, detail="文本太长了")
    return cleaned


def _file_id(apps, app_id: str, value, user: AppUser, existing_id: str | None) -> str:
    if not isinstance(value, str) or not is_uuid(value):
        raise HTTPException(status_code=400, detail="图片无效")
    stored = apps.get(StoredFile, value)
    if stored is None or stored.app_id != app_id:
        raise HTTPException(status_code=400, detail="图片无效")
    if existing_id == value:
        return value
    if stored.owner_id != user.id:
        raise HTTPException(status_code=400, detail="图片无效")
    return value
