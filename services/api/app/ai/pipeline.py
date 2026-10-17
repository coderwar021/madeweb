from __future__ import annotations

import logging
import secrets
import threading
import time

from sqlalchemy import func, select

from app.ai.compile import compile_schema
from app.ai.model import create_draft, edit_draft, explain_source
from app.ai.planner import slug_base
from app.ai.seed import seed_marketplace
from app.models import Application, AppVersion, GenerationJob
from app.settings import Settings
from app.util import dumps, loads, new_id, utcnow
from awp_schema import security_scan

log = logging.getLogger("awp.pipeline")

STEPS = (
    ("intent", "Understanding your idea...", "理解你的想法"),
    ("database", "Designing database...", "设计数据结构"),
    ("interface", "Building interface...", "搭建界面"),
    ("backend", "Creating backend...", "生成后端与权限"),
    ("testing", "Testing...", "安全扫描与校验"),
    ("ready", "Ready.", "可以预览了"),
)


def initial_steps() -> list[dict]:
    steps = [{"key": key, "label": label, "zh": zh, "status": "pending"} for key, label, zh in STEPS]
    steps[0]["status"] = "running"
    return steps


def enqueue(settings: Settings, job_id: str) -> None:
    if settings.fast_pipeline:
        process_job(job_id, settings)
        return
    threading.Thread(target=process_job, args=(job_id, settings), daemon=True).start()


def process_job(job_id: str, settings: Settings) -> None:
    platform = settings.platform_factory()
    apps = settings.apps_factory()
    try:
        job = platform.get(GenerationJob, job_id)
        app = platform.get(Application, job.app_id) if job else None
        if job is None or app is None:
            if job is not None:
                _fail(platform, job, "intent", "网站不存在")
            return
        if job.kind == "create":
            _create(platform, apps, settings, job, app)
        else:
            _edit(platform, settings, job, app)
        platform.commit()
        apps.commit()
    except Exception:
        platform.rollback()
        apps.rollback()
        log.exception("pipeline failed")
        _mark_failed(settings, job_id)
    finally:
        platform.close()
        apps.close()


def _create(platform, apps, settings: Settings, job: GenerationJob, app: Application) -> None:
    _beat(platform, settings, job, "intent", "done")
    _beat(platform, settings, job, "database", "running")
    draft, source = create_draft(job.prompt, settings)
    _beat(platform, settings, job, "database", "done")
    _beat(platform, settings, job, "interface", "running")
    if not draft.get("pages"):
        _fail(platform, job, "interface", "没有生成页面")
        return
    _beat(platform, settings, job, "interface", "done")
    _beat(platform, settings, job, "backend", "running")
    schema = compile_schema(draft, 1)
    _beat(platform, settings, job, "backend", "done")
    _beat(platform, settings, job, "testing", "running")
    report = security_scan(schema)
    if not report["ok"]:
        _fail(platform, job, "testing", "安全校验没有通过")
        return
    version = _save_version(platform, app, schema, "模型生成" if source == "model" else "本地模板", 1)
    app.name = schema["name"][:40]
    app.description = schema["description"][:200]
    app.template = schema["template"]
    app.slug = _unique_slug(platform, slug_base(schema), app.id)
    app.current_version_id = version.id
    app.updated_at = utcnow()
    if schema["template"] == "marketplace":
        seed_marketplace(apps, settings, app.id)
    _succeed(platform, settings, job, app, 1, report, explain_source(source), source)


def _edit(platform, settings: Settings, job: GenerationJob, app: Application) -> None:
    current = platform.get(AppVersion, app.current_version_id) if app.current_version_id else None
    if current is None:
        _fail(platform, job, "intent", "还没有可以修改的版本")
        return
    updated, message = edit_draft(loads(current.schema_json), job.prompt, settings)
    _beat(platform, settings, job, "intent", "done")
    if updated is None:
        if message.startswith("这个功能已经"):
            _finish_unchanged(platform, job, app, current.version, message)
        else:
            _fail(platform, job, "database", message)
        return
    _beat(platform, settings, job, "database", "done")
    _beat(platform, settings, job, "interface", "done")
    _beat(platform, settings, job, "backend", "running")
    next_version = int(
        platform.scalar(select(func.max(AppVersion.version)).where(AppVersion.app_id == app.id)) or 0
    ) + 1
    schema = compile_schema(updated, next_version)
    _beat(platform, settings, job, "backend", "done")
    _beat(platform, settings, job, "testing", "running")
    report = security_scan(schema)
    if not report["ok"]:
        _fail(platform, job, "testing", "安全校验没有通过")
        return
    version = _save_version(platform, app, schema, message, next_version)
    app.current_version_id = version.id
    app.updated_at = utcnow()
    _succeed(platform, settings, job, app, next_version, report, f"已保存为 v{next_version}")


def _save_version(platform, app: Application, schema: dict, message: str, number: int) -> AppVersion:
    version = AppVersion(
        id=new_id(),
        app_id=app.id,
        version=number,
        schema_json=dumps(schema),
        message=message[:200],
        created_at=utcnow(),
    )
    platform.add(version)
    platform.flush()
    return version


def _unique_slug(platform, base: str, app_id: str) -> str:
    slug = base
    for _ in range(6):
        found = platform.scalar(select(Application.id).where(Application.slug == slug, Application.id != app_id))
        if found is None:
            return slug
        slug = f"{base}-{secrets.token_hex(2)}"
    return f"{base}-{secrets.token_hex(4)}"


def _beat(platform, settings: Settings, job: GenerationJob, key: str, status: str) -> None:
    steps = loads(job.steps_json)
    for step in steps:
        if step["key"] == key:
            step["status"] = status
    job.steps_json = dumps(steps)
    platform.commit()
    if not settings.fast_pipeline:
        time.sleep(0.55)


def _succeed(platform, settings, job, app, version: int, report: dict, message: str, source: str = "local") -> None:
    _beat(platform, settings, job, "testing", "done")
    _beat(platform, settings, job, "ready", "done")
    job.status = "succeeded"
    job.result_message = message[:300]
    job.result_json = dumps(
        {
            "slug": app.slug,
            "name": app.name,
            "version": version,
            "source": source,
            "scan": [{"id": item["id"], "ok": item["ok"]} for item in report["checks"]],
        }
    )
    platform.commit()


def _finish_unchanged(platform, job, app, version: int, message: str) -> None:
    steps = loads(job.steps_json)
    for step in steps:
        step["status"] = "done"
    job.steps_json = dumps(steps)
    job.status = "succeeded"
    job.result_message = message
    job.result_json = dumps({"slug": app.slug, "name": app.name, "version": version, "scan": []})
    platform.commit()


def _fail(platform, job: GenerationJob, key: str, message: str) -> None:
    steps = loads(job.steps_json)
    for step in steps:
        if step["key"] == key and step["status"] != "done":
            step["status"] = "failed"
    job.steps_json = dumps(steps)
    job.status = "failed"
    job.error = message[:500]
    platform.commit()


def _mark_failed(settings: Settings, job_id: str) -> None:
    platform = settings.platform_factory()
    try:
        job = platform.get(GenerationJob, job_id)
        if job and job.status == "running":
            job.status = "failed"
            job.error = "生成失败，请换一种说法再试一次。"
            platform.commit()
    finally:
        platform.close()
