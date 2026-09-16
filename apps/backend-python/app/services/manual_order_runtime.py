from datetime import datetime
from typing import Optional

from bson import ObjectId

from .metaapi_client import metaapi_service
from .risk import calc_rr
from .order_logging import append_order_log_prices, merge_order_log_payload
from .order_placement import (
    order_placement_fallback_fields,
    place_pending_order_with_limit_fallback,
    sl_limit_fallback_event_message,
)

OPEN_POSITION_STATUSES = {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}
PENDING_ORDER_STATUSES = {"PENDING", "PLACEMENT_PENDING"}
WAITING_TRIGGER_STATUS = "WAITING_TRIGGER"
RETRYABLE_ORDER_TYPES = frozenset({"LIMIT", "SL"})
PARTIAL_EXIT_R = 4.0
PARTIAL_EXIT_FRACTION = 0.5
PRICE_EPSILON = 1e-9


def _utc_now() -> datetime:
    return datetime.utcnow()


def _manual_context(order: dict) -> dict:
    return dict(order.get("manual_context") or {})


def _is_strategy_owned_order(order: dict) -> bool:
    if order.get("trap_reversal_run_id"):
        return True
    if order.get("planner_context"):
        return True
    if order.get("scheduled_trade_id"):
        return True
    if order.get("dry_run"):
        return True
    return False


def _current_price(price: dict) -> float:
    for key in ("bid", "price", "ask"):
        value = price.get(key)
        if value is not None:
            try:
                number = float(value)
                if number > 0:
                    return number
            except (TypeError, ValueError):
                continue
    return 0.0


def _order_event_message(message: str, order: dict) -> str:
    return append_order_log_prices(message, order)


def _save_order_event(
    db,
    user_id: ObjectId,
    order_id: ObjectId,
    event_type: str,
    status: str,
    message: str,
    payload: Optional[dict] = None,
    *,
    symbol: Optional[str] = None,
    broker_info: Optional[dict] = None,
    notify_user: bool = True,
    failure_reason: Optional[str] = None,
    placement_fallback_reason: Optional[str] = None,
):
    db.order_events.insert_one(
        {
            "order_id": order_id,
            "event_type": event_type,
            "status": status,
            "message": message,
            "event_ts_ist": metaapi_service.now_ist(),
            "payload_json": metaapi_service.serialize_payload(payload or {}),
            "failure_reason": failure_reason,
            "broker_info": broker_info or {},
        }
    )
    if notify_user:
        db.notifications.insert_one(
            {
                "user_id": user_id,
                "order_id": order_id,
                "symbol": symbol,
                "category": "orders",
                "event_type": event_type,
                "status": status,
                "activity": message,
                "failure_reason": failure_reason,
                "placement_fallback_reason": placement_fallback_reason,
                "created_at": _utc_now(),
                "broker_info": broker_info or {},
            }
        )


def _risk_reward(order: dict, price: float) -> float:
    entry = float(order.get("entry") or 0)
    stop_loss = float(order.get("stop_loss") or 0)
    risk = abs(entry - stop_loss)
    if entry <= 0 or risk <= PRICE_EPSILON or price <= 0:
        return 0.0
    side = str(order.get("side") or "").upper()
    if side == "SELL":
        return (entry - price) / risk
    return (price - entry) / risk


def _target_reached(order: dict, price: float) -> bool:
    target = order.get("target")
    if target is None:
        return False
    try:
        target_price = float(target)
    except (TypeError, ValueError):
        return False
    if target_price <= 0:
        return False
    side = str(order.get("side") or "").upper()
    if side == "SELL":
        return price <= target_price + PRICE_EPSILON
    return price >= target_price - PRICE_EPSILON


def _is_clean_stop_close(order: dict) -> bool:
    context = _manual_context(order)
    if context.get("partial_booked_4r") or context.get("target_booked"):
        return False
    if not context.get("position_was_open"):
        return False
    realized = order.get("realized_pl")
    if realized is not None:
        try:
            if float(realized) > PRICE_EPSILON:
                return False
        except (TypeError, ValueError):
            pass
    target = order.get("target")
    if target is not None:
        try:
            target_price = float(target)
            entry = float(order.get("entry") or 0)
            stop_loss = float(order.get("stop_loss") or 0)
            side = str(order.get("side") or "").upper()
            if side == "BUY" and target_price > entry + PRICE_EPSILON:
                return True
            if side == "SELL" and target_price < entry - PRICE_EPSILON:
                return True
        except (TypeError, ValueError):
            pass
    return True


class ManualOrderRuntimeManager:
    def active_symbols(self, db, user_oid: ObjectId, account_db_id) -> set[str]:
        docs = db.orders.find(
            {
                "user_id": user_oid,
                "account_id": account_db_id,
                "dry_run": {"$ne": True},
                "$or": [
                    {
                        "manual_context.automatic_trade_management": True,
                        "status": {"$in": list(OPEN_POSITION_STATUSES)},
                    },
                    {
                        "order_type": "LIMIT",
                        "manual_context.cancel_at": {"$ne": None},
                        "status": {"$in": list(PENDING_ORDER_STATUSES)},
                    },
                    {
                        "order_type": "SL",
                        "manual_context.conditional_order": True,
                        "status": WAITING_TRIGGER_STATUS,
                    },
                ],
            },
            {"symbol": 1},
        )
        symbols = set()
        for doc in docs:
            if _is_strategy_owned_order(doc):
                continue
            symbol = str(doc.get("symbol") or "").upper()
            if symbol:
                symbols.add(symbol)
        return symbols

    async def handle_tick(self, db, user_id: str, account: dict, price: dict, tick_time: datetime):
        if not account:
            return
        user_oid = ObjectId(user_id)
        await self._process_retryable_closes(db, user_oid, account)

        symbol = str(price.get("symbol") or "").upper()
        current = _current_price(price)
        if not symbol or current <= 0:
            return

        await self._process_cancel_at(db, user_oid, account, symbol, price)
        await self._process_conditional_triggers(db, user_oid, account, symbol, price)
        await self._manage_open_positions(db, user_oid, account, symbol, current)

    async def handle_post_reconcile(self, db, user_id: str, account: dict):
        if not account:
            return
        await self._process_retryable_closes(db, ObjectId(user_id), account)

    async def _process_cancel_at(self, db, user_oid: ObjectId, account: dict, symbol: str, price: dict):
        orders = await db.orders.find_async(
            {
                "user_id": user_oid,
                "account_id": account["_id"],
                "symbol": symbol,
                "order_type": "LIMIT",
                "dry_run": {"$ne": True},
                "status": {"$in": list(PENDING_ORDER_STATUSES)},
                "manual_context.cancel_at": {"$ne": None},
            }
        )
        bid = price.get("bid")
        ask = price.get("ask")
        mid = _current_price(price)
        for order in orders:
            if _is_strategy_owned_order(order):
                continue
            context = _manual_context(order)
            cancel_at = context.get("cancel_at")
            if cancel_at is None:
                continue
            try:
                cancel_at = float(cancel_at)
            except (TypeError, ValueError):
                continue
            side = str(order.get("side") or "").upper()
            tapped = False
            if side == "BUY":
                high = ask if ask is not None else mid
                try:
                    tapped = high is not None and float(high) >= cancel_at - PRICE_EPSILON
                except (TypeError, ValueError):
                    tapped = False
            elif side == "SELL":
                low = bid if bid is not None else mid
                try:
                    tapped = low is not None and float(low) <= cancel_at + PRICE_EPSILON
                except (TypeError, ValueError):
                    tapped = False
            if not tapped:
                continue

            meta_order_id = order.get("meta_order_id")
            broker_info = order.get("broker_info") or {}
            try:
                if meta_order_id:
                    await metaapi_service.cancel_order(account["api_token"], account["account_id"], str(meta_order_id))
                await db.orders.update_one_async(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "failure_reason": "Cancel At tapped",
                            "closed_at": _utc_now(),
                            "updated_at": _utc_now(),
                        }
                    },
                )
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "CANCEL_AT_TRIGGERED",
                    "CANCELLED",
                    _order_event_message(
                        f"{order.get('symbol')} Cancel At {cancel_at} tapped; pending plan cancelled.",
                        order,
                    ),
                    merge_order_log_payload({"cancel_at": cancel_at, "bid": bid, "ask": ask, "price": mid}, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                    notify_user=True,
                )
            except Exception as exc:
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "CANCEL_AT_FAILED",
                    str(order.get("status") or ""),
                    append_order_log_prices(f"{order.get('symbol')} Cancel At cancel failed: {exc}", order),
                    merge_order_log_payload({"error": str(exc), "cancel_at": cancel_at}, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                    notify_user=True,
                )

    async def _process_conditional_triggers(self, db, user_oid: ObjectId, account: dict, symbol: str, price: dict):
        orders = await db.orders.find_async(
            {
                "user_id": user_oid,
                "account_id": account["_id"],
                "symbol": symbol,
                "order_type": "SL",
                "dry_run": {"$ne": True},
                "status": WAITING_TRIGGER_STATUS,
                "manual_context.conditional_order": True,
                "manual_context.conditional_triggered": {"$ne": True},
            }
        )
        bid = price.get("bid")
        ask = price.get("ask")
        mid = _current_price(price)
        for order in orders:
            if _is_strategy_owned_order(order):
                continue
            context = _manual_context(order)
            trigger_raw = context.get("trigger_price")
            if trigger_raw is None:
                continue
            try:
                trigger = float(trigger_raw)
            except (TypeError, ValueError):
                continue
            side = str(order.get("side") or "").upper()
            crossed = False
            if side == "SELL":
                high = ask if ask is not None else mid
                try:
                    crossed = high is not None and float(high) >= trigger - PRICE_EPSILON
                except (TypeError, ValueError):
                    crossed = False
            elif side == "BUY":
                low = bid if bid is not None else mid
                try:
                    crossed = low is not None and float(low) <= trigger + PRICE_EPSILON
                except (TypeError, ValueError):
                    crossed = False
            if not crossed:
                continue

            claimed = await db.orders.find_one_and_update_async(
                {
                    "_id": order["_id"],
                    "status": WAITING_TRIGGER_STATUS,
                    "manual_context.conditional_triggered": {"$ne": True},
                },
                {
                    "$set": {
                        "status": "PLACEMENT_PENDING",
                        "manual_context.conditional_triggered": True,
                        "manual_context.conditional_triggered_at": _utc_now(),
                        "updated_at": _utc_now(),
                    }
                },
            )
            if not claimed:
                continue

            broker_info = order.get("broker_info") or {}
            _save_order_event(
                db,
                user_oid,
                order["_id"],
                "CONDITIONAL_TRIGGERED",
                "PLACEMENT_PENDING",
                _order_event_message(
                    f"{order.get('symbol')} trigger {trigger} crossed; placing SL order.",
                    order,
                ),
                merge_order_log_payload(
                    {"trigger_price": trigger, "bid": bid, "ask": ask, "price": mid},
                    source=order,
                ),
                symbol=order.get("symbol"),
                broker_info=broker_info,
            )

            placement_payload = {
                "symbol": order.get("symbol"),
                "order_type": "SL",
                "side": order.get("side"),
                "entry": order.get("entry"),
                "stop_loss": order.get("stop_loss"),
                "target": order.get("target"),
                "quantity": order.get("quantity"),
            }
            try:
                placement = await place_pending_order_with_limit_fallback(
                    metaapi_service,
                    account["api_token"],
                    account["account_id"],
                    placement_payload,
                )
            except Exception as exc:
                failure_reason = str(exc)
                await db.orders.update_one_async(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "status": "FAILED",
                            "failure_reason": failure_reason,
                            "updated_at": _utc_now(),
                            "closed_at": _utc_now(),
                        }
                    },
                )
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "CONDITIONAL_PLACEMENT_FAILED",
                    "FAILED",
                    append_order_log_prices(
                        f"{order.get('symbol')} conditional SL placement failed: {failure_reason}",
                        order,
                    ),
                    merge_order_log_payload({"error": failure_reason, "trigger_price": trigger}, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                    failure_reason=failure_reason,
                )
                continue

            result = placement["result"]
            fallback = placement.get("fallback")
            meta_order_id = str(result.get("orderId", ""))
            await db.orders.update_one_async(
                {"_id": order["_id"]},
                {
                    "$set": {
                        "meta_order_id": meta_order_id,
                        "status": "PENDING",
                        "failure_reason": None,
                        "updated_at": _utc_now(),
                        **order_placement_fallback_fields(fallback),
                    }
                },
            )
            if fallback:
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "ORDER_SL_FALLBACK_TO_LIMIT",
                    "PENDING",
                    sl_limit_fallback_event_message(
                        str(order.get("symbol") or ""),
                        str(fallback.get("sl_placement_error") or ""),
                        order,
                    ),
                    merge_order_log_payload(fallback, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                    placement_fallback_reason=str(fallback.get("fallback_reason") or ""),
                )
            placed_label = str(placement.get("order_type") or "SL").upper()
            _save_order_event(
                db,
                user_oid,
                order["_id"],
                "ORDER_PLACED",
                "PENDING",
                _order_event_message(
                    f"{order.get('symbol')} {placed_label} pending order placed after conditional trigger"
                    + (". SL Invalid price — placed LIMIT at same entry/SL/target instead." if fallback else ""),
                    order,
                ),
                merge_order_log_payload(result, source=order),
                symbol=order.get("symbol"),
                broker_info=broker_info,
                placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
            )

    async def _manage_open_positions(self, db, user_oid: ObjectId, account: dict, symbol: str, price: float):
        orders = await db.orders.find_async(
            {
                "user_id": user_oid,
                "account_id": account["_id"],
                "symbol": symbol,
                "dry_run": {"$ne": True},
                "manual_context.automatic_trade_management": True,
                "status": {"$in": list(OPEN_POSITION_STATUSES)},
            }
        )
        for order in orders:
            if _is_strategy_owned_order(order):
                continue
            context = _manual_context(order)
            if not context.get("automatic_trade_management"):
                continue

            if str(order.get("status") or "").upper() in OPEN_POSITION_STATUSES and not context.get("position_was_open"):
                await db.orders.update_one_async(
                    {"_id": order["_id"]},
                    {"$set": {"manual_context.position_was_open": True, "updated_at": _utc_now()}},
                )
                order.setdefault("manual_context", context)["position_was_open"] = True
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "MANUAL_POSITION_OPEN",
                    str(order.get("status") or ""),
                    _order_event_message(f"{order.get('symbol')} manual position is open.", order),
                    merge_order_log_payload(source=order),
                    symbol=order.get("symbol"),
                    broker_info=order.get("broker_info") or {},
                    notify_user=False,
                )

            position_id = order.get("meta_position_id") or order.get("meta_order_id")
            if not position_id:
                continue

            rr = _risk_reward(order, price)
            broker_info = order.get("broker_info") or {}

            if rr >= PARTIAL_EXIT_R and not context.get("partial_booked_4r"):
                open_qty = float(order.get("position_quantity") or order.get("quantity") or 0)
                close_qty = round(open_qty * PARTIAL_EXIT_FRACTION, 2)
                if close_qty > 0:
                    try:
                        await metaapi_service.close_position(
                            account["api_token"],
                            account["account_id"],
                            str(position_id),
                            close_qty,
                        )
                        await db.orders.update_one_async(
                            {"_id": order["_id"]},
                            {
                                "$set": {
                                    "manual_context.partial_booked_4r": True,
                                    "manual_context.partial_booked_4r_at": _utc_now(),
                                    "updated_at": _utc_now(),
                                }
                            },
                        )
                        _save_order_event(
                            db,
                            user_oid,
                            order["_id"],
                            "MANUAL_PARTIAL_4R_BOOKED",
                            str(order.get("status") or ""),
                            _order_event_message(f"{order.get('symbol')} booked 50% at 4R.", order),
                            merge_order_log_payload({"quantity": close_qty, "price": price, "rr": round(rr, 2)}, source=order),
                            symbol=order.get("symbol"),
                            broker_info=broker_info,
                        )
                    except Exception as exc:
                        _save_order_event(
                            db,
                            user_oid,
                            order["_id"],
                            "MANUAL_PARTIAL_4R_FAILED",
                            str(order.get("status") or ""),
                            append_order_log_prices(f"{order.get('symbol')} 4R partial booking failed: {exc}", order),
                            merge_order_log_payload({"error": str(exc), "rr": round(rr, 2)}, source=order),
                            symbol=order.get("symbol"),
                            broker_info=broker_info,
                        )
                continue

            context = _manual_context((await db.orders.find_one_async({"_id": order["_id"]})) or order)
            if context.get("target_booked") or order.get("target") is None:
                continue
            if not _target_reached(order, price):
                continue

            open_qty = float(order.get("position_quantity") or order.get("quantity") or 0)
            if open_qty <= 0:
                continue
            try:
                await metaapi_service.close_position(
                    account["api_token"],
                    account["account_id"],
                    str(position_id),
                    open_qty,
                )
                await db.orders.update_one_async(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "manual_context.target_booked": True,
                            "manual_context.target_booked_at": _utc_now(),
                            "updated_at": _utc_now(),
                        }
                    },
                )
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "MANUAL_TARGET_EXIT_SENT",
                    str(order.get("status") or ""),
                    _order_event_message(f"{order.get('symbol')} target exit sent for remaining quantity.", order),
                    merge_order_log_payload({"quantity": open_qty, "price": price, "target": order.get("target")}, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                )
            except Exception as exc:
                _save_order_event(
                    db,
                    user_oid,
                    order["_id"],
                    "MANUAL_TARGET_EXIT_FAILED",
                    str(order.get("status") or ""),
                    append_order_log_prices(f"{order.get('symbol')} target exit failed: {exc}", order),
                    merge_order_log_payload({"error": str(exc), "target": order.get("target")}, source=order),
                    symbol=order.get("symbol"),
                    broker_info=broker_info,
                )

    async def _process_retryable_closes(self, db, user_oid: ObjectId, account: dict):
        candidates = await db.orders.find_async(
            {
                "user_id": user_oid,
                "account_id": account["_id"],
                "status": "CLOSED",
                "order_type": {"$in": list(RETRYABLE_ORDER_TYPES)},
                "manual_context.retryable_order": True,
                "manual_context.retry_used": False,
                "manual_context.position_was_open": True,
            }
        )
        for order in candidates:
            if _is_strategy_owned_order(order):
                continue
            if not _is_clean_stop_close(order):
                continue
            claimed = await db.orders.find_one_and_update_async(
                {"_id": order["_id"], "manual_context.retry_used": False},
                {"$set": {"manual_context.retry_used": True, "updated_at": _utc_now()}},
            )
            if not claimed:
                continue
            await self._place_retry_order(db, user_oid, account, claimed)

    async def _place_retry_order(self, db, user_oid: ObjectId, account: dict, parent_order: dict):
        broker_info = parent_order.get("broker_info") or {}
        parent_context = _manual_context(parent_order)
        _save_order_event(
            db,
            user_oid,
            parent_order["_id"],
            "MANUAL_RETRY_TRIGGERED",
            "CLOSED",
            _order_event_message(f"{parent_order.get('symbol')} clean stop hit. Re-placing once as SL order.", parent_order),
            merge_order_log_payload(source=parent_order),
            symbol=parent_order.get("symbol"),
            broker_info=broker_info,
        )

        child_doc = {
            "user_id": user_oid,
            "account_id": account["_id"],
            "symbol": parent_order.get("symbol"),
            "order_type": "SL",
            "side": parent_order.get("side"),
            "entry": parent_order.get("entry"),
            "stop_loss": parent_order.get("stop_loss"),
            "target": parent_order.get("target"),
            "comment": (parent_order.get("comment") or "").strip() or "Retry SL order",
            "quantity": parent_order.get("quantity"),
            "risk_amount": parent_order.get("risk_amount"),
            "sl_pips": parent_order.get("sl_pips"),
            "rr_ratio": calc_rr(
                parent_order.get("side"),
                parent_order.get("entry"),
                parent_order.get("stop_loss"),
                parent_order.get("target"),
            ),
            "meta_order_id": None,
            "status": "PLACEMENT_PENDING",
            "failure_reason": None,
            "copy_group_id": parent_order.get("copy_group_id"),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "opened_at": _utc_now(),
            "closed_at": None,
            "last_broker_seen_at": None,
            "is_open_position": False,
            "position_quantity": None,
            "realized_pl": None,
            "unrealized_pl": None,
            "broker_info": broker_info,
            "manual_context": {
                "retryable_order": False,
                "automatic_trade_management": bool(parent_context.get("automatic_trade_management", True)),
                "retry_used": False,
                "partial_booked_4r": False,
                "target_booked": False,
                "position_was_open": False,
                "parent_order_id": str(parent_order["_id"]),
                "is_retry_child": True,
            },
        }
        insert_result = await db.orders.insert_one_async(child_doc)
        child_doc["_id"] = insert_result.inserted_id
        placement_payload = {
            "symbol": child_doc["symbol"],
            "order_type": child_doc["order_type"],
            "side": child_doc["side"],
            "entry": child_doc["entry"],
            "stop_loss": child_doc["stop_loss"],
            "target": child_doc["target"],
            "quantity": child_doc["quantity"],
        }

        try:
            placement = await place_pending_order_with_limit_fallback(
                metaapi_service,
                account["api_token"],
                account["account_id"],
                placement_payload,
            )
        except Exception as exc:
            failure_reason = str(exc)
            await db.orders.update_one_async(
                {"_id": child_doc["_id"]},
                {"$set": {"status": "FAILED", "failure_reason": failure_reason, "updated_at": _utc_now()}},
            )
            failure_message = append_order_log_prices(
                f"{parent_order.get('symbol')} retry SL order placement failed: {failure_reason}",
                child_doc,
            )
            failure_payload = merge_order_log_payload(
                {"child_order_id": str(child_doc["_id"]), "error": failure_reason},
                source=child_doc,
            )
            _save_order_event(
                db,
                user_oid,
                parent_order["_id"],
                "MANUAL_RETRY_ORDER_FAILED",
                "FAILED",
                failure_message,
                failure_payload,
                symbol=parent_order.get("symbol"),
                broker_info=broker_info,
                failure_reason=failure_reason,
            )
            _save_order_event(
                db,
                user_oid,
                child_doc["_id"],
                "ORDER_PLACEMENT_FAILED",
                "FAILED",
                failure_message,
                merge_order_log_payload({"error": failure_reason, "parent_order_id": str(parent_order["_id"])}, source=child_doc),
                symbol=child_doc.get("symbol"),
                broker_info=broker_info,
                failure_reason=failure_reason,
                notify_user=False,
            )
            return

        result = placement["result"]
        fallback = placement.get("fallback")
        child_updates = {
            "meta_order_id": str(result.get("orderId", "")),
            "status": "PENDING",
            "updated_at": _utc_now(),
            **order_placement_fallback_fields(fallback),
        }
        await db.orders.update_one_async({"_id": child_doc["_id"]}, {"$set": child_updates})
        child_doc.update(child_updates)

        if fallback:
            fallback_message = sl_limit_fallback_event_message(
                str(parent_order.get("symbol") or ""),
                str(fallback.get("sl_placement_error") or ""),
                child_doc,
                retry=True,
            )
            fallback_payload = merge_order_log_payload(fallback, source=child_doc)
            _save_order_event(
                db,
                user_oid,
                parent_order["_id"],
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                fallback_message,
                merge_order_log_payload({**fallback, "child_order_id": str(child_doc["_id"])}, source=child_doc),
                symbol=parent_order.get("symbol"),
                broker_info=broker_info,
                placement_fallback_reason=str(fallback.get("fallback_reason") or ""),
            )
            _save_order_event(
                db,
                user_oid,
                child_doc["_id"],
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                fallback_message,
                fallback_payload,
                symbol=child_doc.get("symbol"),
                broker_info=broker_info,
                notify_user=False,
            )

        placed_label = "LIMIT" if fallback else "SL"
        _save_order_event(
            db,
            user_oid,
            parent_order["_id"],
            "MANUAL_RETRY_ORDER_PLACED",
            "PENDING",
            _order_event_message(
                f"{parent_order.get('symbol')} retry {placed_label} order placed."
                + (" SL Invalid price — used LIMIT fallback at same prices." if fallback else ""),
                child_doc,
            ),
            merge_order_log_payload(
                {"child_order_id": str(child_doc["_id"]), "meta_order_id": child_updates["meta_order_id"]},
                source=child_doc,
            ),
            symbol=parent_order.get("symbol"),
            broker_info=broker_info,
            placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
        )
        _save_order_event(
            db,
            user_oid,
            child_doc["_id"],
            "ORDER_PLACED",
            "PENDING",
            _order_event_message(
                f"{child_doc.get('symbol')} retry {placed_label} pending order placed."
                + (" SL Invalid price — used LIMIT fallback at same prices." if fallback else ""),
                child_doc,
            ),
            merge_order_log_payload(result, source=child_doc),
            symbol=child_doc.get("symbol"),
            broker_info=broker_info,
            placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
        )


manual_order_runtime_manager = ManualOrderRuntimeManager()
