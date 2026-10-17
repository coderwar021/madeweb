"""Deployment agent.

The agent opens an outbound connection to the platform, verifies signed tasks,
and accepts only a fixed action list. It does not run a shell and it does not
attach the host engine socket.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from awp_security.signing import canonical, generate_keypair, sign_bytes, verify_bytes

ALLOWED = {"DEPLOY", "START", "STOP", "RESTART", "ROLLBACK", "STATUS", "LOGS"}
ALLOWED_KEYS = {"task_id", "action", "image", "port", "app_id", "version", "timestamp", "nonce"}
IMAGE_RE = __import__("re").compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*:[A-Za-z0-9][A-Za-z0-9._-]{0,64}$"
)


def agent_message(timestamp: str, nonce: str, method: str, path: str, body: bytes) -> bytes:
    import hashlib

    digest = hashlib.sha256(body).hexdigest()
    return f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{digest}".encode()


def evaluate(payload: dict) -> tuple[bool, str]:
    if not isinstance(payload, dict) or set(payload) - ALLOWED_KEYS:
        return False, "payload rejected"
    action = payload.get("action")
    if action not in ALLOWED:
        return False, "action not allowed"
    image = payload.get("image")
    if not isinstance(image, str) or not IMAGE_RE.match(image) or ".." in image:
        return False, "image rejected"
    port = payload.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        return False, "port rejected"
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or abs(int(time.time()) - timestamp) > 7 * 24 * 3600:
        return False, "stale task"
    if not isinstance(payload.get("nonce"), str) or not isinstance(payload.get("task_id"), str):
        return False, "nonce rejected"
    if not isinstance(payload.get("app_id"), str) or isinstance(payload.get("version"), bool) or not isinstance(payload.get("version"), int):
        return False, "payload rejected"
    return True, "accepted"


def apply_task(state: dict, payload: dict) -> tuple[bool, str]:
    ok, reason = evaluate(payload)
    if not ok:
        return False, reason
    if payload["task_id"] in state["applied"]:
        return True, "already applied"
    action = payload["action"]
    if action in {"DEPLOY", "ROLLBACK"}:
        state["version"] = payload["version"]
        state["image"] = payload["image"]
        state["status"] = "running"
        detail = f"rehearsed {action} {payload['image']}"
    elif action == "STOP":
        state["status"] = "stopped"
        detail = "stopped"
    elif action in {"START", "RESTART"}:
        state["status"] = "running"
        detail = action.lower()
    elif action == "LOGS":
        detail = "deployment-agent: no container logs in local rehearsal"
        state["logs"] = detail
    else:
        detail = state.get("status", "unknown")
    state["applied"].append(payload["task_id"])
    return True, detail


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Web Platform deployment agent")
    parser.add_argument("mode", choices=["enroll", "run"])
    parser.add_argument("--api", required=True)
    parser.add_argument("--token")
    parser.add_argument("--state", default=str(Path(__file__).resolve().parent / "state" / "agent.json"))
    args = parser.parse_args()
    state_path = Path(args.state)
    if args.mode == "enroll":
        if not args.token:
            raise SystemExit("enroll requires --token")
        enroll(args.api.rstrip("/"), args.token, state_path)
        return
    run(args.api.rstrip("/"), state_path)


def enroll(api: str, token: str, state_path: Path) -> None:
    private, public = generate_keypair()
    body = json.dumps({"token": token, "publicKey": public.decode()}).encode()
    response = _open(urllib.request.Request(api + "/api/v1/agent/enroll", data=body, method="POST", headers={"Content-Type": "application/json"}))
    state = {
        "agent_id": response["agentId"],
        "private_key": private.decode(),
        "platform_public_key": response["platformPublicKey"],
        "applied": [],
        "status": "stopped",
        "version": None,
        "image": None,
        "logs": "",
    }
    _save(state_path, state)
    print(f"enrolled {state['agent_id']}")


def run(api: str, state_path: Path) -> None:
    state = _load(state_path)
    while True:
        try:
            _signed(api, "POST", "/api/v1/agent/heartbeat", b"{}", state)
            listed = _signed(api, "GET", "/api/v1/agent/tasks", b"", state)
            for task in listed.get("tasks", []):
                _handle(api, state, task)
            _save(state_path, state)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            print(f"agent waiting: {exc.__class__.__name__}", file=sys.stderr)
        time.sleep(2)


def _handle(api: str, state: dict, task: dict) -> None:
    payload = task.get("payload")
    signature = task.get("signature", "")
    if not isinstance(payload, dict) or not verify_bytes(state["platform_public_key"].encode(), canonical(payload), signature):
        _result(api, state, task.get("id", ""), "failed", "bad signature")
        return
    ok, detail = apply_task(state, payload)
    _result(api, state, payload["task_id"], "succeeded" if ok else "failed", detail)


def _result(api: str, state: dict, task_id: str, status: str, detail: str) -> None:
    if not task_id:
        return
    body = json.dumps({"status": status, "detail": detail[:300]}, separators=(",", ":")).encode()
    _signed(api, "POST", f"/api/v1/agent/tasks/{task_id}/result", body, state)


def _signed(api: str, method: str, path: str, body: bytes, state: dict) -> dict:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    signature = sign_bytes(state["private_key"].encode(), agent_message(timestamp, nonce, method, path, body))
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Id": state["agent_id"],
        "X-Agent-Timestamp": timestamp,
        "X-Agent-Nonce": nonce,
        "X-Agent-Signature": signature,
    }
    request = urllib.request.Request(api + path, data=body if method != "GET" else None, method=method, headers=headers)
    return _open(request)


def _open(request: urllib.request.Request) -> dict:
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode()
    return json.loads(raw) if raw else {}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    path.write_text(json.dumps(state))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    main()
