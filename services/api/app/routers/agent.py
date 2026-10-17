from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.auth import client_ip, hash_token
from app.deps import platform_db
from app.deploy import authenticate_agent
from app.models import AgentNode, Deployment, DeployTask
from app.util import loads, utcnow
from awp_security.redact import redact
from awp_security.signing import load_public_key

router = APIRouter()


@router.post("/agent/enroll")
async def enroll(request: Request, db=Depends(platform_db)):
    _limit(request, f"agent-enroll:{client_ip(request)}", 10, 600)
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid enrollment") from exc
    token = body.get("token") if isinstance(body, dict) else None
    public_key = body.get("publicKey") if isinstance(body, dict) else None
    if not isinstance(token, str) or not isinstance(public_key, str) or len(public_key) > 5000:
        raise HTTPException(status_code=400, detail="invalid enrollment")
    if not load_public_key(public_key.encode()):
        raise HTTPException(status_code=400, detail="invalid agent key")
    agent = db.scalar(select(AgentNode).where(AgentNode.enroll_token_hash == hash_token(token)))
    if agent is None or agent.public_key:
        raise HTTPException(status_code=401, detail="enrollment token is invalid")
    agent.public_key = public_key
    agent.enroll_token_hash = None
    agent.last_seen = utcnow()
    return {
        "agentId": agent.id,
        "platformPublicKey": request.app.state.settings.platform_public_key.decode(),
    }


@router.get("/agent/tasks")
async def tasks(request: Request, db=Depends(platform_db)):
    body = await request.body()
    agent = authenticate_agent(request, db, body)
    rows = db.scalars(select(DeployTask).where(DeployTask.agent_id == agent.id, DeployTask.status == "pending")).all()
    return {
        "tasks": [
            {"id": row.id, "payload": loads(row.payload_json), "signature": row.signature}
            for row in rows
        ]
    }


@router.post("/agent/heartbeat")
async def heartbeat(request: Request, db=Depends(platform_db)):
    body = await request.body()
    agent = authenticate_agent(request, db, body)
    agent.last_seen = utcnow()
    return {"ok": True, "status": "online"}


@router.post("/agent/tasks/{task_id}/result")
async def result(task_id: str, request: Request, db=Depends(platform_db)):
    body = await request.body()
    agent = authenticate_agent(request, db, body)
    try:
        payload = json.loads(body.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid result") from exc
    if not isinstance(payload, dict) or payload.get("status") not in {"succeeded", "failed"}:
        raise HTTPException(status_code=400, detail="invalid result")
    if set(payload) - {"status", "detail"}:
        raise HTTPException(status_code=400, detail="invalid result")
    task = db.get(DeployTask, task_id)
    if task is None or task.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != "pending":
        raise HTTPException(status_code=409, detail="task already finished")
    detail = redact(str(payload.get("detail") or ""))[:300]
    task.status = payload["status"]
    task.detail = detail
    task.finished_at = utcnow()
    deployment = db.get(Deployment, task.deployment_id)
    if deployment is not None:
        deployment.status = payload["status"]
        deployment.error = detail if payload["status"] == "failed" else None
    return {"ok": True}


def _limit(request: Request, key: str, limit: int, window: int) -> None:
    if not request.app.state.limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")
