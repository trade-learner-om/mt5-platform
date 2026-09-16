from datetime import datetime, timezone
from typing import Any

from app.database.mongodb import audit_logs_collection, system_logs_collection


async def write_audit_log(event: str, username: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    await audit_logs_collection().insert_one(
        {
            "event": event,
            "username": username,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        }
    )


async def write_system_log(level: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    await system_logs_collection().insert_one(
        {
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        }
    )
