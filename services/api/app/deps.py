from __future__ import annotations

from fastapi import Request


def platform_db(request: Request):
    db = request.app.state.settings.platform_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def apps_db(request: Request):
    db = request.app.state.settings.apps_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
