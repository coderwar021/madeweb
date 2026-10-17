from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import init_databases, purge_expired
from app.routers import agent, apps, auth, runtime, users
from app.settings import Settings
from awp_security.redact import RedactFilter
from awp_security.signing import generate_keypair

log = logging.getLogger("awp")


class BodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/upload"):
            return await call_next(request)
        raw = request.headers.get("content-length")
        if raw and raw.isdigit() and int(raw) > 100_000:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        return await call_next(request)


def _load_keys(settings: Settings) -> None:
    folder = settings.data_dir / "keys"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    private_path = folder / "platform_ed25519.pem"
    public_path = folder / "platform_ed25519.pub"
    if not private_path.exists():
        private, public = generate_keypair()
        private_path.write_bytes(private)
        public_path.write_bytes(public)
        try:
            private_path.chmod(0o600)
        except OSError:
            pass
    private = private_path.read_bytes()
    key = serialization.load_pem_private_key(private, password=None)
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public)
    settings.platform_private_key = private
    settings.platform_public_key = public


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _install_redact()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        platform_factory, apps_factory = init_databases(settings)
        settings.platform_factory = platform_factory
        settings.apps_factory = apps_factory
        _load_keys(settings)
        purge_expired(settings, platform_factory, apps_factory)
        yield

    app = FastAPI(title="AI Web Platform", lifespan=lifespan, redirect_slashes=False)
    app.state.settings = settings
    from app.auth import RateLimiter

    app.state.limiter = RateLimiter()
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Agent-Id", "X-Agent-Timestamp", "X-Agent-Nonce", "X-Agent-Signature"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            return await http_exception_handler(request, exc)
        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)
        log.exception("request failed")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(apps.router, prefix="/api/v1")
    app.include_router(runtime.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    return app


def _install_redact() -> None:
    root = logging.getLogger()
    if not any(isinstance(item, RedactFilter) for item in root.filters):
        root.addFilter(RedactFilter())


app = create_app()
