from __future__ import annotations

import contextvars
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

AUDIT_COLLECTION = "platform_audit_logs"
APP_NAME = "forex"

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def get_request_id() -> str:
    return request_id_var.get() or ""


def set_request_context(*, request_id: str = "", user_id: str = "", session_id: str = "") -> None:
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if session_id:
        session_id_var.set(session_id)


def new_request_id() -> str:
    return uuid.uuid4().hex


def write_audit(
    db,
    *,
    level: str,
    category: str,
    event: str,
    message: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    app: str = APP_NAME,
) -> None:
    doc = {
        "ts": datetime.now(timezone.utc),
        "app": app,
        "level": str(level or "INFO").upper(),
        "category": category,
        "event": event,
        "user_id": user_id or user_id_var.get() or None,
        "session_id": session_id or session_id_var.get() or None,
        "request_id": get_request_id() or None,
        "message": message,
        "metadata": metadata or {},
    }
    db[AUDIT_COLLECTION].insert_one(doc)


def configure_json_logging() -> None:
    """Backward-compatible entry point; configures full application logging."""
    from .logging_config import configure_application_logging

    configure_application_logging()
