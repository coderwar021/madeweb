from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    AppBase,
    Application,
    AppSession,
    AppUser,
    AppVersion,
    Deployment,
    GenerationJob,
    Like,
    PlatformBase,
    Record,
    StoredFile,
)
from app.settings import Settings
from app.util import as_utc, utcnow


def make_engine(url: str):
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _record):
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _ensure_user_columns(engine) -> None:
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(platform_users)").fetchall()
        present = {row[1] for row in rows}
        columns = {
            "role": "VARCHAR(16) DEFAULT 'user'",
            "status": "VARCHAR(16) DEFAULT 'active'",
            "user_group": "VARCHAR(32) DEFAULT 'default'",
            "quota": "INTEGER DEFAULT 20",
            "used_quota": "INTEGER DEFAULT 0",
        }
        for name, spec in columns.items():
            if name not in present:
                conn.exec_driver_sql(f"ALTER TABLE platform_users ADD COLUMN {name} {spec}")


def init_databases(settings: Settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        settings.data_dir.chmod(0o700)
    except OSError:
        pass
    platform_engine = make_engine(settings.platform_url)
    apps_engine = make_engine(settings.apps_url)
    PlatformBase.metadata.create_all(platform_engine)
    _ensure_user_columns(platform_engine)
    AppBase.metadata.create_all(apps_engine)
    platform_factory = sessionmaker(bind=platform_engine, expire_on_commit=False)
    apps_factory = sessionmaker(bind=apps_engine, expire_on_commit=False)
    return platform_factory, apps_factory


def purge_expired(settings: Settings, platform_factory, apps_factory) -> int:
    cutoff = utcnow() - timedelta(days=settings.retention_days)
    removed = 0
    platform = platform_factory()
    apps = apps_factory()
    try:
        old = platform.scalars(select(Application).where(Application.deleted_at.is_not(None))).all()
        for app in old:
            deleted_at = as_utc(app.deleted_at)
            if deleted_at is None or deleted_at > cutoff:
                continue
            _purge_app_data(settings, platform, apps, app)
            removed += 1
        platform.commit()
        apps.commit()
    except Exception:
        platform.rollback()
        apps.rollback()
        raise
    finally:
        platform.close()
        apps.close()
    return removed


def _purge_app_data(settings: Settings, platform, apps, app: Application) -> None:
    for model in (Record, StoredFile, AppUser, AppSession):
        rows = apps.scalars(select(model).where(model.app_id == app.id)).all()
        for row in rows:
            apps.delete(row)
    upload_root = (settings.data_dir / "uploads" / app.id).resolve()
    base = (settings.data_dir / "uploads").resolve()
    if upload_root.is_relative_to(base) and upload_root.exists():
        for child in upload_root.iterdir():
            if child.is_file():
                child.unlink()
        upload_root.rmdir()
    for model in (AppVersion, GenerationJob, Deployment, Like):
        rows = platform.scalars(select(model).where(model.app_id == app.id)).all()
        for row in rows:
            platform.delete(row)
    platform.delete(app)


def file_path(settings: Settings, app_id: str, file_id: str, ext: str) -> Path:
    from app.util import is_uuid

    if ext not in {".jpg", ".png", ".gif", ".webp"} or not is_uuid(app_id) or not is_uuid(file_id):
        raise ValueError("invalid file path")
    root = (settings.data_dir / "uploads").resolve()
    path = (root / app_id / f"{file_id}{ext}").resolve()
    if not path.is_relative_to(root):
        raise ValueError("invalid file path")
    return path
