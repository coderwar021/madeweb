from __future__ import annotations

import hashlib
import re
import secrets
import time

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.models import AgentNode, AgentNonce, Deployment, DeployTask
from app.settings import Settings
from app.util import as_utc, dumps, new_id, utcnow
from awp_security.signing import canonical, sign_bytes, verify_bytes

ACTIONS = {"DEPLOY", "START", "STOP", "RESTART", "ROLLBACK", "STATUS", "LOGS"}
IMAGE_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*:[A-Za-z0-9][A-Za-z0-9._-]{0,64}$"
)


def deployment_image(app_id: str, version: int) -> str:
    return f"registry/app/{app_id.replace('-', '')[:12]}:v{version}"


def queue_task(db, settings: Settings, agent: AgentNode, deployment: Deployment, action: str, app_id: str, version: int) -> DeployTask:
    if action not in ACTIONS:
        raise HTTPException(status_code=400, detail="不支持的部署动作")
    image = deployment_image(app_id, version)
    if not IMAGE_RE.match(image) or ".." in image:
        raise HTTPException(status_code=500, detail="internal error")
    payload = {
        "task_id": new_id(),
        "action": action,
        "image": image,
        "port": 8080,
        "app_id": app_id,
        "version": version,
        "timestamp": int(time.time()),
        "nonce": secrets.token_urlsafe(16),
    }
    task = DeployTask(
        id=payload["task_id"],
        agent_id=agent.id,
        deployment_id=deployment.id,
        payload_json=dumps(payload),
        signature=sign_bytes(settings.platform_private_key, canonical(payload)),
        status="pending",
        created_at=utcnow(),
    )
    db.add(task)
    return task


def agent_message(timestamp: str, nonce: str, method: str, path: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{digest}".encode()


def authenticate_agent(request: Request, db, body: bytes) -> AgentNode:
    agent_id = request.headers.get("x-agent-id", "")
    timestamp = request.headers.get("x-agent-timestamp", "")
    nonce = request.headers.get("x-agent-nonce", "")
    signature = request.headers.get("x-agent-signature", "")
    agent = db.get(AgentNode, agent_id)
    if agent is None or not agent.public_key:
        raise HTTPException(status_code=401, detail="agent is not enrolled")
    if not timestamp.isdigit() or abs(int(timestamp) - int(time.time())) > 60:
        raise HTTPException(status_code=401, detail="stale agent request")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce):
        raise HTTPException(status_code=401, detail="invalid nonce")
    seen = db.scalar(select(AgentNonce).where(AgentNonce.agent_id == agent.id, AgentNonce.nonce == nonce))
    if seen is not None:
        raise HTTPException(status_code=401, detail="replayed agent request")
    message = agent_message(timestamp, nonce, request.method, request.url.path, body)
    if not verify_bytes(agent.public_key.encode(), message, signature):
        raise HTTPException(status_code=401, detail="bad agent signature")
    db.add(AgentNonce(id=new_id(), agent_id=agent.id, nonce=nonce, seen_at=utcnow()))
    agent.last_seen = utcnow()
    return agent


def agent_online(agent: AgentNode) -> str:
    if not agent.public_key:
        return "pending"
    seen = as_utc(agent.last_seen)
    if seen is not None and (utcnow() - seen).total_seconds() < 20:
        return "online"
    return "offline"
