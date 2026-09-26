"""Dispatch deferred market-open orders after Monday 04:30 IST."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId

from .order_logging import append_order_log_prices, merge_order_log_payload
from .order_placement import (
    DEFERRED_MARKET_OPEN_STATUS,
    is_market_closed_error,
    order_placement_fallback_fields,
    place_pending_order_with_limit_fallback,
    sl_limit_fallback_event_message,
)
from .metaapi_client import metaapi_service

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.utcnow()


async def process_due_deferred_orders(db, user_id, account: dict) -> int:
    """Place due DEFERRED_MARKET_OPEN orders for one account. Returns placements attempted."""
    if not account or not account.get("_id"):
        return 0
    user_oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
    now = _utc_now()
    docs = await db.orders.find_async(
        {
            "user_id": user_oid,
            "account_id": account["_id"],
            "status": DEFERRED_MARKET_OPEN_STATUS,
            "place_after": {"$lte": now},
            "dry_run": {"$ne": True},
        }
    )
    if not docs:
        return 0
    placed = 0
    for doc in docs:
        try:
            await _place_one_deferred(db, account, doc)
            placed += 1
        except Exception:
            logger.exception(
                "Deferred market-open placement failed | order=%s account=%s",
                doc.get("_id"),
                account.get("_id"),
            )
    return placed


async def _place_one_deferred(db, account: dict, doc: dict) -> None:
    order_id = doc["_id"]
    broker_info = doc.get("broker_info") or {}
    payload = {
        "symbol": doc["symbol"],
        "order_type": str(doc.get("order_type") or "").upper(),
        "side": str(doc.get("side") or "").upper(),
        "entry": float(doc["entry"]),
        "stop_loss": float(doc["stop_loss"]),
        "target": doc.get("target"),
        "quantity": float(doc["quantity"]),
    }
    logger.info(
        "Placing deferred market-open order | order=%s symbol=%s side=%s type=%s entry=%s",
        order_id,
        payload["symbol"],
        payload["side"],
        payload["order_type"],
        payload["entry"],
    )
    try:
        placement = await place_pending_order_with_limit_fallback(
            metaapi_service,
            account["api_token"],
            account["account_id"],
            payload,
        )
    except Exception as exc:
        if is_market_closed_error(exc):
            logger.info(
                "Deferred order still market-closed; will retry | order=%s error=%s",
                order_id,
                exc,
            )
            await db.orders.update_one_async(
                {"_id": order_id},
                {"$set": {"failure_reason": str(exc), "updated_at": _utc_now()}},
            )
            return
        failure_reason = str(exc)
        await db.orders.update_one_async(
            {"_id": order_id},
            {
                "$set": {
                    "status": "FAILED",
                    "failure_reason": failure_reason,
                    "updated_at": _utc_now(),
                    "closed_at": _utc_now(),
                }
            },
        )
        db.order_events.insert_one(
            {
                "order_id": order_id,
                "event_type": "ORDER_PLACEMENT_FAILED",
                "status": "FAILED",
                "message": append_order_log_prices(
                    f"{doc.get('symbol')} deferred market-open placement failed: {failure_reason}",
                    doc,
                ),
                "event_ts_ist": metaapi_service.now_ist(),
                "payload": merge_order_log_payload({"error": failure_reason}, source=doc),
                "created_at": _utc_now(),
                "symbol": doc.get("symbol"),
                "broker_info": broker_info,
                "failure_reason": failure_reason,
            }
        )
        return

    result = placement.get("result") or {}
    fallback = placement.get("fallback")
    meta_order_id = str(result.get("orderId") or result.get("id") or "")
    updates = {
        "meta_order_id": meta_order_id,
        "status": "PENDING",
        "failure_reason": None,
        "updated_at": _utc_now(),
        **order_placement_fallback_fields(fallback),
    }
    await db.orders.update_one_async({"_id": order_id}, {"$set": updates})
    if fallback:
        db.order_events.insert_one(
            {
                "order_id": order_id,
                "event_type": "ORDER_SL_FALLBACK_TO_LIMIT",
                "status": "PENDING",
                "message": sl_limit_fallback_event_message(
                    str(doc.get("symbol") or ""),
                    str(fallback.get("sl_placement_error") or ""),
                    doc,
                ),
                "event_ts_ist": metaapi_service.now_ist(),
                "payload": merge_order_log_payload(fallback, source=doc),
                "created_at": _utc_now(),
                "symbol": doc.get("symbol"),
                "broker_info": broker_info,
                "placement_fallback_reason": fallback.get("fallback_reason"),
            }
        )
    placed_label = str(placement.get("order_type") or doc.get("order_type") or "").upper()
    db.order_events.insert_one(
        {
            "order_id": order_id,
            "event_type": "ORDER_PLACED",
            "status": "PENDING",
            "message": append_order_log_prices(
                f"{doc.get('symbol')} deferred {placed_label} placed after Monday 04:30 IST open",
                {**doc, **updates},
            ),
            "event_ts_ist": metaapi_service.now_ist(),
            "payload": merge_order_log_payload(result, source={**doc, **updates}),
            "created_at": _utc_now(),
            "symbol": doc.get("symbol"),
            "broker_info": broker_info,
        }
    )
    logger.info(
        "Deferred market-open order placed | order=%s meta_order_id=%s type=%s",
        order_id,
        meta_order_id,
        placed_label,
    )
