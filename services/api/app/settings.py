from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass
class Settings:
    data_dir: Path
    database_url: str | None = None
    apps_database_url: str | None = None
    admin_emails: set[str] = field(default_factory=set)
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    fast_pipeline: bool = False
    bcrypt_rounds: int = 12
    cookie_secure: bool = False
    public_api_base: str = "http://127.0.0.1:8000"
    retention_days: int = 30
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    repo_root: Path = field(default_factory=_repo_root)
    platform_private_key: bytes = b""
    platform_public_key: bytes = b""
    platform_factory: Any = None
    apps_factory: Any = None

    @classmethod
    def from_env(cls) -> Settings:
        root = _repo_root()
        data_dir = Path(os.environ.get("DATA_DIR", root / "data")).expanduser()
        admins = {
            item.strip().lower()
            for item in os.environ.get("ADMIN_EMAILS", "").split(",")
            if item.strip()
        }
        origins = [
            item.strip()
            for item in os.environ.get("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
            if item.strip()
        ]
        domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        public = os.environ.get("PUBLIC_API_BASE", "").strip()
        if not public and domain:
            public = f"https://{domain}"
        if not public:
            public = "http://127.0.0.1:8000"
        secure_env = os.environ.get("COOKIE_SECURE", "").strip()
        cookie_secure = secure_env == "1" if secure_env else public.startswith("https://")
        return cls(
            data_dir=data_dir,
            database_url=os.environ.get("DATABASE_URL") or None,
            apps_database_url=os.environ.get("APPS_DATABASE_URL") or None,
            admin_emails=admins,
            ai_api_key=(os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip(),
            ai_base_url=(os.environ.get("AI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1").strip(),
            ai_model=(os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip(),
            fast_pipeline=os.environ.get("PIPELINE_FAST") == "1",
            bcrypt_rounds=int(os.environ.get("BCRYPT_ROUNDS", "12")),
            cookie_secure=cookie_secure,
            public_api_base=public,
            retention_days=int(os.environ.get("RETENTION_DAYS", "30")),
            cors_origins=origins,
            repo_root=root,
        )

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_api_key and self.ai_base_url and self.ai_model)

    @property
    def platform_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'platform.db'}"

    @property
    def apps_url(self) -> str:
        if self.apps_database_url:
            return self.apps_database_url
        return f"sqlite:///{self.data_dir / 'apps.db'}"
