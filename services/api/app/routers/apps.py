from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.access import can_view_app, is_owner, require_owner, schema_of
from app.auth import (
    client_ip,
    hash_token,
    is_operator,
    normalize_name,
    read_platform_session,
    require_csrf,
    require_user,
)
from app.deps import platform_db
from app.deploy import agent_online, deployment_image, queue_task
from app.models import (
    AgentNode,
    Application,
    AppVersion,
    AuditLog,
    Deployment,
    GenerationJob,
    Like,
    Report,
)
from app.ai.pipeline import enqueue, initial_steps
from app.util import dumps, is_uuid, loads, new_id, utcnow
from awp_schema import security_scan
from awp_security.redact import redact

router = APIRouter()


class PromptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["platform", "server"]
    visibility: Literal["private", "unlisted", "public"] = "public"
    agentId: str | None = None


class RollbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["phishing", "malware", "scam", "spam", "impersonation", "other"]
    details: str = ""


class AppealIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    details: str


class OperationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["START", "STOP", "RESTART", "STATUS", "LOGS"]


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class DisableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = ""


@router.post("/apps")
def create_application(payload: PromptIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    prompt = _prompt(payload.prompt)
    _limit(request, f"ai:{user.id}", 10, 60)
    if user.used_quota >= user.quota:
        raise HTTPException(status_code=403, detail="生成次数已用完")
    user.used_quota += 1
    now = utcnow()
    app = Application(
        id=new_id(),
        owner_id=user.id,
        name="生成中",
        slug=f"draft-{secrets.token_hex(4)}",
        description="",
        template="generic",
        visibility="private",
        status="active",
        like_count=0,
        remix_count=0,
        view_count=0,
        created_at=now,
        updated_at=now,
    )
    job = _job(app.id, user.id, "create", prompt, now)
    db.add(app)
    db.add(job)
    db.commit()
    _audit(db, request, user.id, "GENERATE", app.id, detail="create")
    enqueue(request.app.state.settings, job.id)
    return {"jobId": job.id, "appId": app.id}


@router.post("/apps/{app_id}/edits")
def edit_application(app_id: str, payload: PromptIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    if app.current_version_id is None:
        raise HTTPException(status_code=409, detail="网站还在生成")
    prompt = _prompt(payload.prompt)
    _limit(request, f"ai:{user.id}", 10, 60)
    job = _job(app.id, user.id, "edit", prompt, utcnow())
    db.add(job)
    db.commit()
    _audit(db, request, user.id, "EDIT", app.id, detail="schema diff")
    enqueue(request.app.state.settings, job.id)
    return {"jobId": job.id, "appId": app.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request, db=Depends(platform_db)):
    user, _session = require_user(request, db)
    job = db.get(GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "id": job.id,
        "appId": job.app_id,
        "status": job.status,
        "steps": loads(job.steps_json),
        "prompt": job.prompt,
        "message": job.result_message,
        "error": job.error,
        "result": loads(job.result_json) if job.result_json else None,
    }


@router.get("/apps")
def my_apps(request: Request, db=Depends(platform_db)):
    user, _session = require_user(request, db)
    rows = db.scalars(
        select(Application)
        .where(Application.owner_id == user.id, Application.deleted_at.is_(None))
        .order_by(Application.updated_at.desc())
    ).all()
    return {"apps": [_summary(db, row, user.id) for row in rows]}


@router.get("/apps/{app_id}")
def get_app(app_id: str, request: Request, db=Depends(platform_db)):
    user, _session = require_user(request, db)
    app = _owned(db, user, app_id)
    versions = db.scalars(select(AppVersion).where(AppVersion.app_id == app.id).order_by(AppVersion.version.desc())).all()
    deployments = db.scalars(
        select(Deployment).where(Deployment.app_id == app.id).order_by(Deployment.created_at.desc()).limit(10)
    ).all()
    return {
        "app": _summary(db, app, user.id),
        "versions": [
            {"id": item.id, "version": item.version, "message": item.message, "createdAt": item.created_at.isoformat()}
            for item in versions
        ],
        "deployments": [
            {
                "id": item.id,
                "version": item.version,
                "target": item.target,
                "action": item.action,
                "status": item.status,
                "error": item.error,
                "createdAt": item.created_at.isoformat(),
            }
            for item in deployments
        ],
    }


@router.delete("/apps/{app_id}")
def delete_app(app_id: str, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    app.deleted_at = utcnow()
    app.updated_at = utcnow()
    _audit(db, request, user.id, "DELETE", app.id, detail="soft delete")
    return {"ok": True}


@router.post("/apps/{app_id}/publish")
def publish(app_id: str, payload: PublishIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    version = _current_version(db, app)
    agent = None
    status = "succeeded"
    if payload.target == "server":
        agent = _owned_agent(db, user.id, payload.agentId)
        status = "queued"
    app.visibility = payload.visibility
    app.published_version_id = version.id
    app.published_target = payload.target
    app.agent_id = agent.id if agent else app.agent_id
    app.updated_at = utcnow()
    deployment = _deployment(app, version.version, payload.target, "DEPLOY", status, agent.id if agent else None)
    db.add(deployment)
    db.flush()
    if agent is not None:
        queue_task(db, request.app.state.settings, agent, deployment, "DEPLOY", app.id, version.version)
    _audit(db, request, user.id, "PUBLISH", app.id, version.version, payload.target)
    return {"deployment": _deployment_out(deployment), "app": _summary(db, app, user.id), "image": deployment_image(app.id, version.version)}


@router.post("/apps/{app_id}/operations")
def operate(app_id: str, payload: OperationIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    if app.published_target != "server" or not app.agent_id:
        raise HTTPException(status_code=400, detail="这个网站没有连接到你的服务器")
    version = _current_version(db, app)
    agent = _owned_agent(db, user.id, app.agent_id)
    deployment = _deployment(app, version.version, "server", payload.action, "queued", agent.id)
    db.add(deployment)
    db.flush()
    queue_task(db, request.app.state.settings, agent, deployment, payload.action, app.id, version.version)
    _audit(db, request, user.id, payload.action, app.id, version.version, "fixed agent action")
    return {"deployment": _deployment_out(deployment)}


@router.post("/apps/{app_id}/rollback")
def rollback(app_id: str, payload: RollbackIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    version = db.scalar(select(AppVersion).where(AppVersion.app_id == app.id, AppVersion.version == payload.version))
    if version is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    app.current_version_id = version.id
    app.updated_at = utcnow()
    deployment_out = None
    if app.published_version_id:
        app.published_version_id = version.id
        status = "succeeded"
        agent = None
        if app.published_target == "server" and app.agent_id:
            agent = _owned_agent(db, user.id, app.agent_id)
            status = "queued"
        deployment = _deployment(app, version.version, app.published_target or "platform", "ROLLBACK", status, agent.id if agent else None)
        db.add(deployment)
        db.flush()
        if agent is not None:
            queue_task(db, request.app.state.settings, agent, deployment, "ROLLBACK", app.id, version.version)
        deployment_out = _deployment_out(deployment)
    _audit(db, request, user.id, "ROLLBACK", app.id, version.version)
    return {"app": _summary(db, app, user.id), "deployment": deployment_out}


@router.post("/apps/{app_id}/remix")
def remix(app_id: str, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    source = _visible(db, request, app_id)
    version_id = source.published_version_id or (source.current_version_id if is_owner(user, source) else None)
    if version_id is None:
        raise HTTPException(status_code=404, detail="网站不存在")
    schema = schema_of(db.get(AppVersion, version_id))
    schema["version"] = "1.0.0"
    report = security_scan(schema)
    if not report["ok"]:
        raise HTTPException(status_code=400, detail="这个版本不能被 remix")
    now = utcnow()
    name = schema["name"]
    suffix = " 的副本"
    if len(name) + len(suffix) <= 40:
        name = name + suffix
    app = Application(
        id=new_id(),
        owner_id=user.id,
        name=name,
        slug=f"remix-{secrets.token_hex(4)}",
        description=schema.get("description", "")[:200],
        template=schema.get("template", "generic"),
        visibility="private",
        status="active",
        remix_of_id=source.id,
        like_count=0,
        remix_count=0,
        view_count=0,
        created_at=now,
        updated_at=now,
    )
    version = AppVersion(id=new_id(), app_id=app.id, version=1, schema_json=dumps(schema), message="Remix", created_at=now)
    app.current_version_id = version.id
    source.remix_count += 1
    db.add(app)
    db.add(version)
    _audit(db, request, user.id, "REMIX", app.id, 1, source.id)
    return {"app": _summary(db, app, user.id)}


@router.post("/apps/{app_id}/like")
def like(app_id: str, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _visible(db, request, app_id)
    existing = db.scalar(select(Like).where(Like.user_id == user.id, Like.app_id == app.id))
    if existing:
        db.delete(existing)
        app.like_count = max(0, app.like_count - 1)
        liked = False
    else:
        db.add(Like(id=new_id(), user_id=user.id, app_id=app.id, created_at=utcnow()))
        app.like_count += 1
        liked = True
    return {"liked": liked, "likeCount": app.like_count}


@router.post("/apps/{app_id}/report")
def report(app_id: str, payload: ReportIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    _limit(request, f"report:{user.id}", 5, 3600)
    app = _visible(db, request, app_id)
    details = payload.details.strip()
    if len(details) > 500:
        raise HTTPException(status_code=400, detail="说明太长了")
    db.add(
        Report(
            id=new_id(),
            reporter_id=user.id,
            app_id=app.id,
            reason=payload.reason,
            details=details,
            created_at=utcnow(),
        )
    )
    _audit(db, request, user.id, "REPORT", app.id, detail=payload.reason)
    return {"ok": True}


@router.post("/apps/{app_id}/appeal")
def appeal(app_id: str, payload: AppealIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    app = _owned(db, user, app_id)
    if app.status != "disabled":
        raise HTTPException(status_code=400, detail="这个网站没有被下架")
    details = payload.details.strip()
    if not details or len(details) > 500:
        raise HTTPException(status_code=400, detail="请写一段 500 字以内的说明")
    app.appeal_note = details
    app.updated_at = utcnow()
    _audit(db, request, user.id, "APPEAL", app.id)
    return {"ok": True}


@router.get("/explore")
def explore(request: Request, sort: str = "trending", db=Depends(platform_db)):
    found = read_platform_session(request, db)
    user = found[0] if found else None
    score = Application.like_count * 2 + Application.remix_count * 3 + Application.view_count
    order = {
        "new": Application.created_at.desc(),
        "popular": Application.like_count.desc(),
        "remixed": Application.remix_count.desc(),
        "used": Application.view_count.desc(),
    }.get(sort, score.desc())
    rows = db.scalars(
        select(Application)
        .where(
            Application.deleted_at.is_(None),
            Application.status == "active",
            Application.visibility == "public",
            Application.published_version_id.is_not(None),
        )
        .order_by(order)
        .limit(60)
    ).all()
    liked: set[str] = set()
    if user is not None and rows:
        liked = set(
            db.scalars(select(Like.app_id).where(Like.user_id == user.id, Like.app_id.in_([row.id for row in rows]))).all()
        )
    return {"apps": [_public_card(row, row.id in liked) for row in rows]}


@router.get("/sites/{slug}")
def site(slug: str, request: Request, draft: bool = False, db=Depends(platform_db)):
    app = db.scalar(select(Application).where(Application.slug == slug))
    found = read_platform_session(request, db)
    user = found[0] if found else None
    if app is None or not can_view_app(user, app):
        raise HTTPException(status_code=404, detail="网站不存在")
    if app.current_version_id is None:
        raise HTTPException(status_code=409, detail="网站还在生成")
    owner = is_owner(user, app)
    if owner and (draft or app.published_version_id is None):
        version = db.get(AppVersion, app.current_version_id)
    elif app.published_version_id:
        version = db.get(AppVersion, app.published_version_id)
    else:
        raise HTTPException(status_code=404, detail="网站不存在")
    if version is None:
        raise HTTPException(status_code=404, detail="网站不存在")
    if not owner and app.visibility == "public" and app.status == "active":
        app.view_count += 1
    return {
        "app": _public_card(app, False) | {"owner": owner, "status": app.status, "dirty": app.current_version_id != app.published_version_id},
        "version": version.version,
        "schema": schema_of(version),
    }


@router.post("/agents")
def create_agent(payload: AgentIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    _limit(request, f"enroll:{user.id}", 10, 3600)
    name = normalize_name(payload.name)
    token = secrets.token_urlsafe(24)
    agent = AgentNode(
        id=new_id(),
        owner_id=user.id,
        name=name,
        enroll_token_hash=hash_token(token),
        created_at=utcnow(),
    )
    db.add(agent)
    settings = request.app.state.settings
    _audit(db, request, user.id, "AGENT_ENROLL_TOKEN", detail=agent.id)
    return {
        "agent": {"id": agent.id, "name": agent.name, "status": "pending"},
        "enrollToken": token,
        "enrollCommand": _command(settings, "enroll", token),
        "runCommand": _command(settings, "run", None),
    }


@router.get("/agents")
def list_agents(request: Request, db=Depends(platform_db)):
    user, _session = require_user(request, db)
    rows = db.scalars(select(AgentNode).where(AgentNode.owner_id == user.id).order_by(AgentNode.created_at.desc())).all()
    return {
        "agents": [
            {"id": row.id, "name": row.name, "status": agent_online(row), "lastSeen": row.last_seen.isoformat() if row.last_seen else None}
            for row in rows
        ]
    }


@router.get("/moderation/queue")
def moderation_queue(request: Request, db=Depends(platform_db)):
    user, _session = require_user(request, db)
    _admin(request, user)
    reports = db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100)).all()
    disabled = db.scalars(select(Application).where(Application.status == "disabled", Application.deleted_at.is_(None))).all()
    return {
        "reports": [
            {
                "id": item.id,
                "appId": item.app_id,
                "reason": item.reason,
                "details": item.details,
                "createdAt": item.created_at.isoformat(),
            }
            for item in reports
        ],
        "disabled": [
            {"id": item.id, "name": item.name, "slug": item.slug, "appeal": item.appeal_note}
            for item in disabled
        ],
    }


@router.post("/moderation/apps/{app_id}/disable")
def disable_app(app_id: str, payload: DisableIn, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    _admin(request, user)
    app = db.get(Application, app_id)
    if app is None or app.deleted_at is not None:
        raise HTTPException(status_code=404, detail="网站不存在")
    app.status = "disabled"
    app.updated_at = utcnow()
    _audit(db, request, user.id, "DISABLE", app.id, detail=payload.note[:200])
    return {"ok": True}


@router.post("/moderation/apps/{app_id}/restore")
def restore_app(app_id: str, request: Request, db=Depends(platform_db)):
    user, session = require_user(request, db)
    require_csrf(request, session)
    _admin(request, user)
    app = db.get(Application, app_id)
    if app is None or app.deleted_at is not None:
        raise HTTPException(status_code=404, detail="网站不存在")
    app.status = "active"
    app.updated_at = utcnow()
    _audit(db, request, user.id, "RESTORE", app.id)
    return {"ok": True}


def _job(app_id: str, user_id: str, kind: str, prompt: str, now) -> GenerationJob:
    return GenerationJob(
        id=new_id(),
        app_id=app_id,
        user_id=user_id,
        kind=kind,
        prompt=prompt,
        status="running",
        steps_json=dumps(initial_steps()),
        result_message="",
        created_at=now,
    )


def _prompt(value: str) -> str:
    text = value.strip()
    if not text or len(text) > 2000:
        raise HTTPException(status_code=400, detail="请用一句话描述你想做的网站")
    return text


def _owned(db, user, app_id: str) -> Application:
    if not is_uuid(app_id):
        raise HTTPException(status_code=404, detail="网站不存在")
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="网站不存在")
    require_owner(user, app)
    return app


def _visible(db, request: Request, app_id: str) -> Application:
    if not is_uuid(app_id):
        raise HTTPException(status_code=404, detail="网站不存在")
    app = db.get(Application, app_id)
    found = read_platform_session(request, db)
    user = found[0] if found else None
    if app is None or not can_view_app(user, app):
        raise HTTPException(status_code=404, detail="网站不存在")
    return app


def _current_version(db, app: Application) -> AppVersion:
    if app.current_version_id is None:
        raise HTTPException(status_code=409, detail="网站还在生成")
    version = db.get(AppVersion, app.current_version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="网站还在生成")
    return version


def _owned_agent(db, user_id: str, agent_id: str | None) -> AgentNode:
    if not agent_id or not is_uuid(agent_id):
        raise HTTPException(status_code=400, detail="请先安装并连接 Agent")
    agent = db.get(AgentNode, agent_id)
    if agent is None or agent.owner_id != user_id or not agent.public_key:
        raise HTTPException(status_code=400, detail="Agent 还没有完成安装")
    return agent


def _deployment(app: Application, version: int, target: str, action: str, status: str, agent_id: str | None) -> Deployment:
    return Deployment(
        id=new_id(),
        app_id=app.id,
        version=version,
        target=target,
        action=action,
        status=status,
        agent_id=agent_id,
        created_at=utcnow(),
    )


def _deployment_out(item: Deployment) -> dict:
    return {"id": item.id, "version": item.version, "target": item.target, "action": item.action, "status": item.status}


def _summary(db, app: Application, user_id: str) -> dict:
    current = db.get(AppVersion, app.current_version_id) if app.current_version_id else None
    published = db.get(AppVersion, app.published_version_id) if app.published_version_id else None
    liked = db.scalar(select(Like.id).where(Like.user_id == user_id, Like.app_id == app.id))
    return {
        "id": app.id,
        "slug": app.slug,
        "name": app.name,
        "description": app.description,
        "template": app.template,
        "visibility": app.visibility,
        "status": app.status,
        "published": published is not None,
        "publishedTarget": app.published_target,
        "currentVersion": current.version if current else None,
        "publishedVersion": published.version if published else None,
        "dirty": current is not None and (published is None or current.id != published.id),
        "likeCount": app.like_count,
        "remixCount": app.remix_count,
        "viewCount": app.view_count,
        "liked": liked is not None,
        "remixOf": app.remix_of_id,
        "updatedAt": app.updated_at.isoformat(),
    }


def _public_card(app: Application, liked: bool) -> dict:
    return {
        "id": app.id,
        "slug": app.slug,
        "name": app.name,
        "description": app.description,
        "template": app.template,
        "visibility": app.visibility,
        "likeCount": app.like_count,
        "remixCount": app.remix_count,
        "viewCount": app.view_count,
        "liked": liked,
    }


def _audit(db, request: Request, user_id: str, action: str, app_id: str | None = None, version: int | None = None, detail: str = "") -> None:
    db.add(
        AuditLog(
            id=new_id(),
            user_id=user_id,
            ip=client_ip(request)[:64],
            action=action,
            app_id=app_id,
            version=version,
            detail=redact(detail)[:300],
            created_at=utcnow(),
        )
    )


def _admin(request: Request, user) -> None:
    if not is_operator(user, request.app.state.settings):
        raise HTTPException(status_code=403, detail="没有审核权限")


def _limit(request: Request, key: str, limit: int, window: int) -> None:
    if not request.app.state.limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _command(settings, kind: str, token: str | None) -> str:
    base = "cd agent/deployment-agent && PYTHONPATH=../../packages/security python3 agent.py"
    if kind == "enroll":
        return f"{base} enroll --api {_quote(settings.public_api_base)} --token {_quote(token or '')}"
    return f"{base} run --api {_quote(settings.public_api_base)}"
