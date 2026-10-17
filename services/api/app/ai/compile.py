from __future__ import annotations

import copy

ROLES = ["owner", "admin", "editor", "user", "guest"]


def build_permissions(entities: list[dict]) -> list[dict]:
    perms: list[dict] = []
    for entity in entities:
        name = entity["name"]
        access = entity["access"]
        if access == "public":
            perms.append({"role": "guest", "resource": name, "action": "view", "scope": "all"})
            for role in ("user", "editor"):
                perms.append({"role": role, "resource": name, "action": "view", "scope": "all"})
                perms.append({"role": role, "resource": name, "action": "create", "scope": "all"})
            perms.append({"role": "user", "resource": name, "action": "update", "scope": "own"})
            perms.append({"role": "user", "resource": name, "action": "delete", "scope": "own"})
            perms.append({"role": "editor", "resource": name, "action": "update", "scope": "all"})
            perms.append({"role": "editor", "resource": name, "action": "delete", "scope": "own"})
        elif access == "participant":
            for role in ("user", "editor"):
                perms.append({"role": role, "resource": name, "action": "view", "scope": "participant"})
                perms.append({"role": role, "resource": name, "action": "create", "scope": "all"})
        else:
            for role in ("user", "editor"):
                perms.append({"role": role, "resource": name, "action": "view", "scope": "own"})
                perms.append({"role": role, "resource": name, "action": "create", "scope": "all"})
                perms.append({"role": role, "resource": name, "action": "update", "scope": "own"})
                perms.append({"role": role, "resource": name, "action": "delete", "scope": "own"})
    return perms


def compile_schema(schema: dict, version: int) -> dict:
    compiled = copy.deepcopy(schema)
    compiled["version"] = f"{version}.0.0"
    compiled["roles"] = list(ROLES)
    compiled["permissions"] = build_permissions(compiled["entities"])
    compiled["workflows"] = []
    compiled["generator"] = "schema-compiler"
    tagline = compiled.get("theme", {}).get("tagline", "")
    compiled["description"] = str(compiled.get("description") or tagline)[:200]
    return compiled
