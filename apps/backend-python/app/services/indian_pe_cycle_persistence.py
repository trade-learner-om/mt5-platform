"""Persistence for Indian PE→Stock→CE cycle backtests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

STRATEGY_TYPE = "indian_pe_stock_ce"
RESULTS_COLLECTION = "indian_pe_cycle_backtests"
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 50


def _utc_now() -> datetime:
    return datetime.utcnow()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    return str(value)


def save_pe_cycle_backtest(
    db,
    *,
    user_id: ObjectId,
    account_id: ObjectId,
    underlying: str,
    from_date: str,
    to_date: str,
    simulation: dict,
) -> ObjectId:
    now = _utc_now()
    doc = {
        "user_id": user_id,
        "account_id": account_id,
        "strategy_type": STRATEGY_TYPE,
        "underlying": str(underlying).upper(),
        "display_symbol": str(underlying).upper(),
        "from_date": from_date,
        "to_date": to_date,
        "status": "COMPLETED",
        "summary": {
            "cumulative_pnl": simulation.get("cumulative_pnl"),
            "event_count": simulation.get("event_count"),
            "final_state": simulation.get("final_state"),
            "lot_size": simulation.get("lot_size"),
        },
        "events": list(simulation.get("events") or []),
        "simulation": simulation,
        "created_at": now,
        "updated_at": now,
    }
    return db[RESULTS_COLLECTION].insert_one(doc).inserted_id


def list_pe_cycle_backtests(db, user_id: ObjectId, *, limit: int = DEFAULT_PAGE_LIMIT) -> list[dict]:
    page_limit = max(1, min(MAX_PAGE_LIMIT, int(limit or DEFAULT_PAGE_LIMIT)))
    docs = list(
        db[RESULTS_COLLECTION]
        .find({"user_id": user_id, "strategy_type": STRATEGY_TYPE}, {"simulation": 0})
        .sort("created_at", -1)
        .limit(page_limit)
    )
    return [serialize_pe_cycle_list_item(doc) for doc in docs]


def get_pe_cycle_backtest(db, user_id: ObjectId, backtest_id: ObjectId) -> Optional[dict]:
    doc = db[RESULTS_COLLECTION].find_one({"_id": backtest_id, "user_id": user_id, "strategy_type": STRATEGY_TYPE})
    if not doc:
        return None
    return serialize_pe_cycle_detail(doc)


def delete_pe_cycle_backtest(db, user_id: ObjectId, backtest_id: ObjectId) -> bool:
    result = db[RESULTS_COLLECTION].delete_one({"_id": backtest_id, "user_id": user_id, "strategy_type": STRATEGY_TYPE})
    return result.deleted_count > 0


def serialize_pe_cycle_list_item(doc: dict) -> dict:
    summary = doc.get("summary") or {}
    return {
        "backtest_id": str(doc.get("_id")),
        "strategy_type": STRATEGY_TYPE,
        "underlying": doc.get("underlying"),
        "display_symbol": doc.get("display_symbol") or doc.get("underlying"),
        "from_date": doc.get("from_date"),
        "to_date": doc.get("to_date"),
        "status": doc.get("status"),
        "cumulative_pnl": summary.get("cumulative_pnl"),
        "event_count": summary.get("event_count"),
        "final_state": summary.get("final_state"),
        "created_at": _iso(doc.get("created_at")),
    }


def serialize_pe_cycle_detail(doc: dict) -> dict:
    item = serialize_pe_cycle_list_item(doc)
    item["events"] = list(doc.get("events") or [])
    item["summary"] = dict(doc.get("summary") or {})
    item["simulation"] = doc.get("simulation") or {}
    return item
