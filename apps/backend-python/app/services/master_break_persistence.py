from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from .master_break_settings import STRATEGY_TYPE

RUN_COLLECTION = "master_break_runs"
STATUS_RUNNING = "RUNNING"
STATUS_STOPPED = "STOPPED"


def _utc_now() -> datetime:
    return datetime.utcnow()


def save_run(db, doc: dict[str, Any]) -> ObjectId:
    payload = dict(doc)
    now = _utc_now()
    payload.setdefault("strategy_type", STRATEGY_TYPE)
    payload.setdefault("status", STATUS_RUNNING)
    payload.setdefault("created_at", now)
    payload["updated_at"] = now
    result = db[RUN_COLLECTION].insert_one(payload)
    return result.inserted_id


def update_run(db, run_id: ObjectId, updates: dict[str, Any]) -> bool:
    payload = dict(updates or {})
    payload["updated_at"] = _utc_now()
    result = db[RUN_COLLECTION].update_one({"_id": run_id, "strategy_type": STRATEGY_TYPE}, {"$set": payload})
    return result.matched_count > 0


def get_run(db, run_id: ObjectId, user_id: Optional[ObjectId] = None) -> Optional[dict]:
    query: dict[str, Any] = {"_id": run_id, "strategy_type": STRATEGY_TYPE}
    if user_id is not None:
        query["user_id"] = user_id
    return db[RUN_COLLECTION].find_one(query)


def list_running_runs(db, user_id: Optional[ObjectId] = None) -> list[dict]:
    query: dict[str, Any] = {"strategy_type": STRATEGY_TYPE, "status": STATUS_RUNNING}
    if user_id is not None:
        query["user_id"] = user_id
    return list(db[RUN_COLLECTION].find(query).sort("updated_at", -1))


def mark_stopped(db, run_id: ObjectId) -> bool:
    return update_run(db, run_id, {"status": STATUS_STOPPED})


def delete_run(db, run_id: ObjectId, user_id: Optional[ObjectId] = None) -> bool:
    query: dict[str, Any] = {"_id": run_id, "strategy_type": STRATEGY_TYPE}
    if user_id is not None:
        query["user_id"] = user_id
    result = db[RUN_COLLECTION].delete_one(query)
    return result.deleted_count > 0
