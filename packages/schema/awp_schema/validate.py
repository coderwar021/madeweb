from __future__ import annotations

import json
import re
from typing import Any

FIELD_TYPES = {
    "string",
    "text",
    "decimal",
    "integer",
    "boolean",
    "enum",
    "file",
    "file[]",
    "user",
    "datetime",
    "relation",
}
ROLES = {"owner", "admin", "editor", "user", "guest"}
ACTIONS = {"view", "create", "update", "delete"}
SCOPES = {"all", "own", "participant"}
ACCESS = {"public", "private", "participant"}
COMPONENTS: dict[str, set[str]] = {
    "Navbar": set(),
    "Hero": {"title", "subtitle"},
    "Search": {"entity", "placeholder"},
    "Filter": {"entity", "field"},
    "ProductGrid": {"source"},
    "CardGrid": {"source"},
    "Form": {"source", "mode"},
    "Table": {"source"},
    "AuthForm": set(),
    "Detail": {"source"},
    "Comment": {"source"},
    "Pagination": set(),
    "EmptyState": {"title"},
}
TOP_LEVEL = {
    "name",
    "version",
    "description",
    "entities",
    "pages",
    "permissions",
    "roles",
    "theme",
    "nav",
    "workflows",
    "template",
    "generator",
}
BANNED_FIELDS = {
    "password",
    "secret",
    "apikey",
    "api_key",
    "token",
    "privatekey",
    "private_key",
    "accesstoken",
    "access_token",
}
FORBIDDEN_KEYS = {
    "dangerouslysetinnerhtml",
    "innerhtml",
    "sql",
    "shell",
    "command",
    "eval",
    "exec",
    "__proto__",
    "prototype",
    "dependencies",
    "packages",
}
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key\s*[:=]|BEGIN [A-Z ]*PRIVATE KEY|\bsk-[A-Za-z0-9]{10,}|password\s*[:=]\s*\S+)"
)
ENTITY_RE = re.compile(r"^[A-Z][A-Za-z0-9]{0,32}$")
FIELD_RE = re.compile(r"^[a-z][A-Za-z0-9]{0,32}$")
ROUTE_RE = re.compile(r"^/([a-zA-Z0-9_:\-./]*)$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class SchemaError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_schema(schema: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema must be an object"]
    raw = json.dumps(schema, ensure_ascii=False)
    if len(raw.encode()) > 200_000:
        errors.append("schema is too large")
    extra = set(schema) - TOP_LEVEL
    if extra:
        errors.append("unknown schema keys: " + ", ".join(sorted(extra)))
    _walk_keys(schema, errors)
    if schema.get("generator") != "schema-compiler":
        errors.append("generator must be schema-compiler")
    if not isinstance(schema.get("name"), str) or not schema["name"].strip():
        errors.append("name is required")
    elif len(schema["name"]) > 40:
        errors.append("name is too long")
    if not VERSION_RE.match(str(schema.get("version", ""))):
        errors.append("version must be semver")
    description = schema.get("description", "")
    if not isinstance(description, str) or len(description) > 200:
        errors.append("description is invalid")
    template = schema.get("template", "generic")
    if template not in {"marketplace", "blog", "booking", "generic"}:
        errors.append("unknown template")
    if schema.get("workflows") not in ([], None) and schema.get("workflows") != []:
        if not isinstance(schema.get("workflows"), list):
            errors.append("workflows must be a list")
        elif schema["workflows"]:
            errors.append("workflows are not enabled")
    roles = schema.get("roles")
    if roles != ["owner", "admin", "editor", "user", "guest"]:
        errors.append("roles must be the platform role set")
    entities = schema.get("entities")
    if not isinstance(entities, list) or not entities:
        errors.append("entities are required")
        entities = []
    if len(entities) > 24:
        errors.append("too many entities")
    entity_names: set[str] = set()
    entity_fields: dict[str, dict] = {}
    for entity in entities:
        _validate_entity(entity, errors, entity_names, entity_fields)
    for entity in entities:
        if not isinstance(entity, dict) or not isinstance(entity.get("fields"), dict):
            continue
        for fname, spec in entity["fields"].items():
            if isinstance(spec, dict) and spec.get("type") == "relation" and spec.get("target") not in entity_names:
                errors.append(f"{entity.get('name')}.{fname} relation target does not exist")
    _validate_permissions(schema.get("permissions"), entity_names, errors)
    pages = schema.get("pages")
    routes: set[str] = set()
    if not isinstance(pages, list) or not pages:
        errors.append("pages are required")
        pages = []
    if len(pages) > 24:
        errors.append("too many pages")
    for page in pages:
        _validate_page(page, entity_names, entity_fields, routes, errors)
    _validate_nav(schema.get("nav", []), routes, errors)
    _validate_theme(schema.get("theme", {}), errors)
    if SECRET_RE.search(raw):
        errors.append("schema contains a secret-like value")
    if "http://" in raw.lower() or "https://" in raw.lower():
        errors.append("schema must not contain urls")
    if ".." in raw or "<script" in raw.lower() or "javascript:" in raw.lower():
        errors.append("schema contains an unsafe string")
    return errors


def security_scan(schema: Any) -> dict[str, Any]:
    errors = validate_schema(schema)
    raw = json.dumps(schema, ensure_ascii=False) if isinstance(schema, dict) else ""
    checks = [
        {"id": "schema", "ok": not errors, "detail": "application definition"},
        {"id": "sqli", "ok": "select " not in raw.lower() and "drop table" not in raw.lower(), "detail": "no raw SQL"},
        {"id": "xss", "ok": "dangerouslysetinnerhtml" not in raw.lower() and "<script" not in raw.lower(), "detail": "no raw HTML"},
        {"id": "ssrf", "ok": "http://" not in raw.lower() and "https://" not in raw.lower(), "detail": "no outbound URL"},
        {"id": "rce", "ok": not _has_forbidden_key(schema), "detail": "no command surface"},
        {"id": "secrets", "ok": not SECRET_RE.search(raw), "detail": "no hardcoded secret"},
        {"id": "traversal", "ok": ".." not in raw, "detail": "no path traversal"},
        {"id": "deps", "ok": isinstance(schema, dict) and "dependencies" not in schema and "packages" not in schema, "detail": "no free dependencies"},
    ]
    for check in checks:
        if not check["ok"] and check["id"] != "schema":
            errors.append(f"{check['id']} failed")
    return {"ok": not errors and all(c["ok"] for c in checks), "checks": checks, "errors": errors}


def _validate_entity(entity: Any, errors: list[str], names: set[str], fields_by_name: dict[str, dict]) -> None:
    if not isinstance(entity, dict):
        errors.append("entity must be an object")
        return
    if set(entity) - {"name", "label", "access", "titleField", "fields", "unique"}:
        errors.append("entity has unknown keys")
    name = entity.get("name")
    if not isinstance(name, str) or not ENTITY_RE.match(name):
        errors.append(f"invalid entity name: {name!r}")
        return
    if name in names:
        errors.append(f"duplicate entity {name}")
    names.add(name)
    if entity.get("access") not in ACCESS:
        errors.append(f"{name} access is invalid")
    label = entity.get("label")
    if not isinstance(label, str) or not label.strip() or len(label) > 40:
        errors.append(f"{name} label is invalid")
    fields = entity.get("fields")
    if not isinstance(fields, dict) or not fields or len(fields) > 32:
        errors.append(f"{name} fields are invalid")
        fields = {}
    fields_by_name[name] = fields
    for fname, spec in fields.items():
        if not FIELD_RE.match(str(fname)) or fname.lower() in BANNED_FIELDS:
            errors.append(f"{name}.{fname} is not an allowed field")
            continue
        if not isinstance(spec, dict) or spec.get("type") not in FIELD_TYPES:
            errors.append(f"{name}.{fname} type is invalid")
            continue
        if set(spec) - {"type", "label", "required", "values", "default", "target", "auto", "participant", "searchable"}:
            errors.append(f"{name}.{fname} has unknown keys")
        if "required" in spec and not isinstance(spec["required"], bool):
            errors.append(f"{name}.{fname} required must be boolean")
        if "searchable" in spec and not isinstance(spec["searchable"], bool):
            errors.append(f"{name}.{fname} searchable must be boolean")
        if not isinstance(spec.get("label"), str) or len(spec["label"]) > 40:
            errors.append(f"{name}.{fname} label is invalid")
        if spec["type"] == "enum":
            values = spec.get("values")
            if not isinstance(values, list) or not 1 <= len(values) <= 12:
                errors.append(f"{name}.{fname} enum is invalid")
            elif any(not isinstance(v, str) or not v or len(v) > 32 for v in values):
                errors.append(f"{name}.{fname} enum values are invalid")
            elif spec.get("default") is not None and spec.get("default") not in values:
                errors.append(f"{name}.{fname} default is invalid")
        if spec["type"] == "relation" and not isinstance(spec.get("target"), str):
            errors.append(f"{name}.{fname} relation target is missing")
        if spec["type"] == "user" and spec.get("auto") not in {None, "current"}:
            errors.append(f"{name}.{fname} user auto is invalid")
        if spec.get("participant") not in {None, True, False}:
            errors.append(f"{name}.{fname} participant flag is invalid")
    title_field = entity.get("titleField")
    if title_field not in fields:
        errors.append(f"{name} titleField is invalid")
    unique = entity.get("unique", [])
    if unique is None:
        unique = []
    if not isinstance(unique, list) or len(unique) > 4 or any(u not in fields for u in unique):
        errors.append(f"{name} unique fields are invalid")


def _validate_permissions(perms: Any, names: set[str], errors: list[str]) -> None:
    if not isinstance(perms, list):
        errors.append("permissions must be a list")
        return
    if len(perms) > 400:
        errors.append("too many permissions")
    for perm in perms:
        if not isinstance(perm, dict):
            errors.append("permission must be an object")
            continue
        if set(perm) - {"role", "resource", "action", "scope"}:
            errors.append("permission has unknown keys")
        if perm.get("role") not in ROLES:
            errors.append("permission role is invalid")
        if perm.get("resource") not in names:
            errors.append("permission resource is invalid")
        if perm.get("action") not in ACTIONS:
            errors.append("permission action is invalid")
        if perm.get("scope", "all") not in SCOPES:
            errors.append("permission scope is invalid")


def _validate_page(page: Any, names: set[str], fields: dict[str, dict], routes: set[str], errors: list[str]) -> None:
    if not isinstance(page, dict):
        errors.append("page must be an object")
        return
    if set(page) - {"page", "id", "title", "route", "layout", "components"}:
        errors.append("page has unknown keys")
    route = page.get("route")
    if not isinstance(route, str) or not ROUTE_RE.match(route) or ".." in route:
        errors.append(f"invalid route {route!r}")
    elif route in routes:
        errors.append(f"duplicate route {route}")
    else:
        routes.add(route)
    if page.get("layout") != "default":
        errors.append("layout must be default")
    title = page.get("page", page.get("title"))
    if not isinstance(title, str) or len(title) > 40:
        errors.append("page title is invalid")
    components = page.get("components")
    if not isinstance(components, list) or len(components) > 12:
        errors.append("page components are invalid")
        return
    for component in components:
        if not isinstance(component, dict) or component.get("type") not in COMPONENTS:
            errors.append("component type is not allowed")
            continue
        allowed = COMPONENTS[component["type"]] | {"type"}
        if set(component) - allowed:
            errors.append(f"{component['type']} has unknown props")
        for key, value in component.items():
            if key == "type":
                continue
            if not isinstance(value, str) or not value or len(value) > 200:
                errors.append(f"{component['type']}.{key} is invalid")
        source = component.get("source") or component.get("entity")
        if component["type"] in {"ProductGrid", "CardGrid", "Form", "Table", "Detail", "Comment", "Search"}:
            if source not in names:
                errors.append(f"{component['type']} references unknown entity")
        if component["type"] == "Filter":
            if component.get("entity") not in names:
                errors.append("filter entity is invalid")
            field_name = component.get("field")
            if not any(field_name in (fields.get(ent) or {}) for ent in names):
                errors.append("filter field is invalid")
        if component["type"] == "Form" and component.get("mode") != "create":
            errors.append("form mode must be create")
        if component["type"] == "Hero":
            if not component.get("title"):
                errors.append("hero title is required")


def _validate_nav(nav: Any, routes: set[str], errors: list[str]) -> None:
    if nav is None:
        return
    if not isinstance(nav, list) or len(nav) > 8:
        errors.append("nav is invalid")
        return
    for item in nav:
        if not isinstance(item, dict) or set(item) - {"label", "route"}:
            errors.append("nav item is invalid")
            continue
        if not isinstance(item.get("label"), str) or not item["label"] or len(item["label"]) > 16:
            errors.append("nav label is invalid")
        if item.get("route") not in routes:
            errors.append("nav route does not exist")


def _validate_theme(theme: Any, errors: list[str]) -> None:
    if not isinstance(theme, dict):
        errors.append("theme must be an object")
        return
    allowed = {"primary", "background", "ink", "logo", "tagline", "currency"}
    if set(theme) - allowed:
        errors.append("theme has unknown keys")
    for key in ("primary", "background", "ink"):
        if not isinstance(theme.get(key), str) or not COLOR_RE.match(theme[key]):
            errors.append(f"theme.{key} must be a color")
    for key, limit in (("logo", 24), ("tagline", 80), ("currency", 8)):
        value = theme.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            errors.append(f"theme.{key} is invalid")
    if theme.get("currency") not in {None, "", "JPY", "CNY", "USD"}:
        errors.append("currency is invalid")


def _walk_keys(value: Any, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                errors.append(f"forbidden key {key}")
            _walk_keys(child, errors)
    elif isinstance(value, list):
        for child in value:
            _walk_keys(child, errors)


def _has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS or _has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_has_forbidden_key(child) for child in value)
    return False
