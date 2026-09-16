from __future__ import annotations

import base64
import json
import math
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from .master_break_settings import STRATEGY_TYPE

RESULTS_COLLECTION = "strategy_results"
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 50
DEFAULT_TRADE_LIMIT = 20
MAX_TRADE_LIMIT = 100


def _utc_now() -> datetime:
    return datetime.utcnow()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + ("Z" if value.tzinfo is None else "")
    return str(value)


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: Optional[str]) -> Optional[dict[str, Any]]:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(str(cursor).encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def encode_result_cursor(created_at: datetime, result_id: ObjectId) -> str:
    return _encode_cursor({"created_at": _iso(created_at), "_id": str(result_id)})


def encode_trade_cursor(index: int) -> str:
    return _encode_cursor({"index": int(index)})


def save_backtest_result(
    db,
    *,
    user_id: ObjectId,
    account_id: Optional[ObjectId],
    symbol: str,
    from_date: str,
    to_date: str,
    settings: dict[str, Any],
    summary: dict[str, Any],
    trades: list[dict[str, Any]],
    rolls: Optional[list[dict[str, Any]]] = None,
    master_rows: Optional[list[dict[str, Any]]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> ObjectId:
    now = _utc_now()
    doc: dict[str, Any] = {
        "user_id": user_id,
        "account_id": account_id,
        "strategy_type": STRATEGY_TYPE,
        "symbol": symbol,
        "display_symbol": symbol,
        "from_date": from_date,
        "to_date": to_date,
        "status": "COMPLETED",
        "settings": dict(settings or {}),
        "summary": dict(summary or {}),
        "trades": list(trades or []),
        "rolls": list(rolls or []),
        "master_rows": list(master_rows or []),
        "trade_count": len(trades or []),
        "master_row_count": len(master_rows or []),
        "created_at": now,
        "updated_at": now,
    }
    if extra:
        doc.update(extra)
    return db[RESULTS_COLLECTION].insert_one(doc).inserted_id


def list_page(
    db,
    user_id: ObjectId,
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
    cursor: Optional[str] = None,
) -> dict[str, Any]:
    page_limit = max(1, min(MAX_PAGE_LIMIT, int(limit or DEFAULT_PAGE_LIMIT)))
    query: dict[str, Any] = {"user_id": user_id, "strategy_type": STRATEGY_TYPE}
    decoded = _decode_cursor(cursor)
    if decoded and decoded.get("created_at") and decoded.get("_id"):
        created_at_raw = decoded["created_at"]
        try:
            created_at = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
            if created_at.tzinfo is not None:
                created_at = created_at.replace(tzinfo=None)
        except ValueError:
            created_at = None
        if created_at is not None:
            query["$or"] = [
                {"created_at": {"$lt": created_at}},
                {"created_at": created_at, "_id": {"$lt": ObjectId(str(decoded["_id"]))}},
            ]

    total_count = db[RESULTS_COLLECTION].count_documents({"user_id": user_id, "strategy_type": STRATEGY_TYPE})
    total_pages = max(1, int(math.ceil(total_count / page_limit))) if total_count else 0
    docs = list(
        db[RESULTS_COLLECTION]
        .find(query, {"trades": 0, "rolls": 0, "master_rows": 0})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(page_limit + 1)
    )
    has_next = len(docs) > page_limit
    page_docs = docs[:page_limit]
    end_cursor = None
    if page_docs:
        last = page_docs[-1]
        end_cursor = encode_result_cursor(last.get("created_at") or _utc_now(), last["_id"])

    results = [serialize_list_item(doc) for doc in page_docs]
    return {
        "results": results,
        "page_info": {
            "total_count": total_count,
            "total_pages": total_pages,
            "limit": page_limit,
            "has_next": has_next,
            "has_next_page": has_next,
            "has_prev": bool(cursor),
            "has_previous_page": bool(cursor),
            "end_cursor": end_cursor,
        },
    }


def get_backtest(db, user_id: ObjectId, result_id: ObjectId) -> Optional[dict]:
    doc = db[RESULTS_COLLECTION].find_one({"_id": result_id, "user_id": user_id, "strategy_type": STRATEGY_TYPE})
    if not doc:
        return None
    return serialize_detail(doc)


def delete_backtest(db, user_id: ObjectId, result_id: ObjectId) -> bool:
    result = db[RESULTS_COLLECTION].delete_one({"_id": result_id, "user_id": user_id, "strategy_type": STRATEGY_TYPE})
    return result.deleted_count > 0


def list_trades_page(
    db,
    user_id: ObjectId,
    result_id: ObjectId,
    *,
    limit: int = DEFAULT_TRADE_LIMIT,
    cursor: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    doc = db[RESULTS_COLLECTION].find_one(
        {"_id": result_id, "user_id": user_id, "strategy_type": STRATEGY_TYPE},
        {"trades": 1, "summary": 1, "trade_count": 1},
    )
    if not doc:
        return None
    trades = list(doc.get("trades") or [])
    total_count = len(trades)
    page_limit = max(1, min(MAX_TRADE_LIMIT, int(limit or DEFAULT_TRADE_LIMIT)))
    start_index = 0
    decoded = _decode_cursor(cursor)
    if decoded and decoded.get("index") is not None:
        start_index = max(0, int(decoded["index"]) + 1)
    end_index = min(total_count, start_index + page_limit)
    page = trades[start_index:end_index]
    has_next = end_index < total_count
    has_prev = start_index > 0
    end_cursor = encode_trade_cursor(end_index - 1) if page else None
    total_pages = max(1, int(math.ceil(total_count / page_limit))) if total_count else 0
    return {
        "trades": page,
        "page_info": {
            "total_count": total_count,
            "total_pages": total_pages,
            "limit": page_limit,
            "start_index": start_index,
            "end_index": max(start_index, end_index - 1) if page else start_index,
            "has_next": has_next,
            "has_next_page": has_next,
            "has_prev": has_prev,
            "has_previous_page": has_prev,
            "end_cursor": end_cursor,
            "showing_from": start_index + 1 if page else 0,
            "showing_to": end_index if page else 0,
        },
    }


def serialize_list_item(doc: dict) -> dict[str, Any]:
    summary = doc.get("summary") or {}
    return {
        "id": str(doc.get("_id")),
        "backtest_id": str(doc.get("_id")),
        "strategy_type": STRATEGY_TYPE,
        "symbol": doc.get("symbol"),
        "display_symbol": doc.get("display_symbol") or doc.get("symbol"),
        "from_date": doc.get("from_date"),
        "to_date": doc.get("to_date"),
        "status": doc.get("status"),
        "summary": dict(summary),
        "trade_count": doc.get("trade_count") if doc.get("trade_count") is not None else summary.get("total_trades"),
        "master_row_count": doc.get("master_row_count"),
        "settings": doc.get("settings") or {},
        "created_at": _iso(doc.get("created_at")),
    }


def serialize_detail(doc: dict) -> dict[str, Any]:
    item = serialize_list_item(doc)
    item["trades"] = list(doc.get("trades") or [])
    item["rolls"] = list(doc.get("rolls") or [])
    item["master_rows"] = list(doc.get("master_rows") or [])
    return item
