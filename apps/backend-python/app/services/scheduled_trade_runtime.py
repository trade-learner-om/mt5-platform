"""Scheduled Break Trade runtime: bar-roll FSM, placement, and order lifecycle sync."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from weakref import WeakKeyDictionary

from bson import ObjectId

from .candle_history import TIMEFRAME_SECONDS, get_chart_candles, normalize_timeframe
from .master_break_levels import coerce_candle_time
from .master_break_risk import quantity_from_risk
from .metaapi_client import metaapi_service
from .order_logging import append_order_log_prices, merge_order_log_payload
from .order_placement import (
    is_invalid_price_error,
    order_placement_fallback_fields,
    place_pending_order_with_limit_fallback,
    sl_limit_fallback_event_message,
)
from .risk import calc_rr, digits_from_symbol_spec, normalize_price_to_symbol, point_size_from_symbol_spec
from .scheduled_trade_levels import (
    ACTIVE_STATUSES,
    CANCELLABLE_STATUSES,
    ORDER_TRACKING_STATUSES,
    PRICE_EPSILON,
    WATCHING_STATUSES,
    entry_sl_for_side,
    is_green,
    is_oversized_signal_candle,
    is_red,
    level_broken_on_close,
    normalize_max_signal_candle_pips,
    normalize_scheduled_timeframe,
    resolve_side_from_level,
    scheduled_pip_size,
    usable_target,
)
from .symbol_resolver import normalize_symbol

logger = logging.getLogger(__name__)

COLLECTION = "scheduled_trades"
EVENTS_COLLECTION = "scheduled_trade_events"


def _utc_now() -> datetime:
    return datetime.utcnow()


def _broker_info_from_account(account: Optional[dict]) -> dict:
    if not account:
        return {}
    meta_profile = account.get("meta_profile") or {}
    broker_info = {
        "account_name": str(account.get("account_name") or meta_profile.get("account_name") or ""),
        "account_id": str(account.get("account_id") or ""),
        "login": str(meta_profile.get("login") or ""),
        "server": str(meta_profile.get("server") or ""),
        "type": str(meta_profile.get("type") or ""),
    }
    return {key: value for key, value in broker_info.items() if value}


def _mid_from_price(price: dict) -> float:
    bid = price.get("bid")
    ask = price.get("ask")
    try:
        bid_f = float(bid) if bid is not None else 0.0
        ask_f = float(ask) if ask is not None else 0.0
    except (TypeError, ValueError):
        bid_f = ask_f = 0.0
    if bid_f > 0 and ask_f > 0:
        return (bid_f + ask_f) / 2.0
    for key in ("price", "bid", "ask"):
        try:
            value = float(price.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _serialize_schedule(doc: dict) -> dict:
    signal = doc.get("signal_candle") or None
    return {
        "id": str(doc.get("_id")),
        "account_id": str(doc.get("account_id") or "") or None,
        "symbol": doc.get("symbol"),
        "timeframe": doc.get("timeframe"),
        "level": doc.get("level"),
        "side": doc.get("side"),
        "risk_amount": doc.get("risk_amount"),
        "target": doc.get("target"),
        "max_signal_candle_pips": doc.get("max_signal_candle_pips"),
        "retryable_order": bool(doc.get("retryable_order")),
        "retry_used": bool(doc.get("retry_used")),
        "status": doc.get("status"),
        "point_size": doc.get("point_size"),
        "pip_size": doc.get("pip_size"),
        "signal_candle": signal,
        "entry": doc.get("entry"),
        "stop_loss": doc.get("stop_loss"),
        "quantity": doc.get("quantity"),
        "order_id": str(doc["order_id"]) if doc.get("order_id") else None,
        "retry_order_id": str(doc["retry_order_id"]) if doc.get("retry_order_id") else None,
        "meta_order_id": str(doc["meta_order_id"]) if doc.get("meta_order_id") else None,
        "retry_meta_order_id": str(doc["retry_meta_order_id"]) if doc.get("retry_meta_order_id") else None,
        "placement_fallback_reason": doc.get("placement_fallback_reason"),
        "placement_order_type": doc.get("placement_order_type"),
        "last_error": doc.get("last_error"),
        "broker_info": doc.get("broker_info") or {},
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
        "armed_at": _iso(doc.get("armed_at")),
        "placed_at": _iso(doc.get("placed_at")),
        "filled_at": _iso(doc.get("filled_at")),
        "exited_at": _iso(doc.get("exited_at")),
    }


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _bar_start(tick_time: datetime, timeframe: str) -> datetime:
    seconds = int(TIMEFRAME_SECONDS[normalize_timeframe(timeframe)])
    if tick_time.tzinfo is not None:
        tick_time = tick_time.replace(tzinfo=None)
    epoch = int(tick_time.replace(tzinfo=timezone.utc).timestamp())
    start_epoch = epoch - (epoch % seconds)
    return datetime.fromtimestamp(start_epoch, tz=timezone.utc).replace(tzinfo=None)


@dataclass
class ExecCandle:
    start: datetime
    open: float
    high: float
    low: float
    close: float

    def update(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.start,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }


@dataclass
class ScheduleRuntime:
    schedule_id: ObjectId
    user_id: ObjectId
    account_id: ObjectId
    symbol: str
    timeframe: str
    current: Optional[ExecCandle] = None
    last_completed_start: Optional[datetime] = None


class ScheduledTradeManager:
    _instance: Optional["ScheduledTradeManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._runtimes: dict[str, ScheduleRuntime] = {}
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = WeakKeyDictionary()
        self._symbol_index: dict[str, set[str]] = {}

    @classmethod
    def instance(cls) -> "ScheduledTradeManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def active_symbols(self, user_id: str, account_db_id) -> set[str]:
        prefix = f"{user_id}:"
        out: set[str] = set()
        for key, runtime in list(self._runtimes.items()):
            if not key.startswith(prefix):
                continue
            if account_db_id is not None and str(runtime.account_id) != str(account_db_id):
                continue
            if runtime.symbol:
                out.add(normalize_symbol(runtime.symbol))
        return out

    def active_symbols_from_db(self, db, user_oid: ObjectId, account_db_id) -> set[str]:
        query: dict[str, Any] = {
            "user_id": user_oid,
            "status": {"$in": list(ACTIVE_STATUSES)},
        }
        if account_db_id is not None:
            query["account_id"] = account_db_id
        docs = list(db[COLLECTION].find(query, {"symbol": 1}))
        return {normalize_symbol(item.get("symbol")) for item in docs if item.get("symbol")}

    async def create_schedule(
        self,
        db,
        user: dict,
        account: dict,
        *,
        symbol: str,
        broker_symbol: str,
        timeframe: str,
        level: float,
        risk_amount: float,
        target: Optional[float],
        retryable_order: bool,
        mid_price: float,
        point_size: float,
        price_digits: int,
        max_signal_candle_pips: Optional[float] = None,
        seed_candles: Optional[list[dict]] = None,
    ) -> dict:
        tf = normalize_scheduled_timeframe(timeframe)
        side = resolve_side_from_level(level, mid_price)
        pip_size = scheduled_pip_size(broker_symbol)
        max_candle_pips = normalize_max_signal_candle_pips(max_signal_candle_pips, broker_symbol)
        now = _utc_now()
        doc = {
            "user_id": user["_id"],
            "account_id": account["_id"],
            "symbol": broker_symbol,
            "requested_symbol": symbol,
            "timeframe": tf,
            "level": float(level),
            "side": side,
            "risk_amount": float(risk_amount),
            "target": float(target) if target is not None else None,
            "max_signal_candle_pips": float(max_candle_pips),
            "retryable_order": bool(retryable_order),
            "retry_used": False,
            "status": "INITIATED",
            "point_size": float(point_size),
            "pip_size": float(pip_size),
            "price_digits": int(price_digits),
            "signal_candle": None,
            "entry": None,
            "stop_loss": None,
            "quantity": None,
            "order_id": None,
            "retry_order_id": None,
            "meta_order_id": None,
            "retry_meta_order_id": None,
            "placement_fallback_reason": None,
            "placement_order_type": None,
            "last_error": None,
            "broker_info": _broker_info_from_account(account),
            "created_at": now,
            "updated_at": now,
            "armed_at": None,
            "placed_at": None,
            "filled_at": None,
            "exited_at": None,
            "events": [],
        }
        result = await db[COLLECTION].insert_one_async(doc)
        doc["_id"] = result.inserted_id
        self._register_runtime(doc, seed_candles=seed_candles or [])
        await self._append_event(
            db,
            doc,
            "SCHEDULE_CREATED",
            "INITIATED",
            f"{broker_symbol} {side} schedule created at level {level} on {tf}",
            {
                "level": level,
                "side": side,
                "timeframe": tf,
                "mid_price": mid_price,
                "max_signal_candle_pips": max_candle_pips,
            },
        )
        return _serialize_schedule(doc)

    async def list_schedules(self, db, user_id: ObjectId, *, account_id: Optional[ObjectId] = None, include_terminal: bool = True) -> list[dict]:
        query: dict[str, Any] = {"user_id": user_id}
        if account_id is not None:
            query["account_id"] = account_id
        if not include_terminal:
            query["status"] = {"$in": list(ACTIVE_STATUSES)}
        docs = await db[COLLECTION].find_async(query)
        docs.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
        return [_serialize_schedule(doc) for doc in docs]

    async def cancel_schedule(self, db, user: dict, account: dict, schedule_id: ObjectId) -> dict:
        doc = await db[COLLECTION].find_one_async({"_id": schedule_id, "user_id": user["_id"]})
        if not doc:
            raise ValueError("Scheduled trade not found")
        status = str(doc.get("status") or "")
        if status not in CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel schedule in status {status}")

        if status in {"ORDER_PLACED", "RETRY_ORDER_PLACED"}:
            order_id = doc.get("retry_order_id") if status.startswith("RETRY_") else doc.get("order_id")
            if order_id:
                order = await db.orders.find_one_async({"_id": order_id, "user_id": user["_id"]})
                if order and order.get("meta_order_id") and str(order.get("status") or "").upper() in {"PENDING", "PLACEMENT_PENDING"}:
                    try:
                        await metaapi_service.cancel_order(
                            account["api_token"],
                            account["account_id"],
                            str(order["meta_order_id"]),
                        )
                    except Exception as exc:
                        logger.warning("Scheduled trade cancel broker order failed: %s", exc)
                    await db.orders.update_one_async(
                        {"_id": order["_id"]},
                        {"$set": {"status": "CANCELLED", "updated_at": _utc_now(), "closed_at": _utc_now()}},
                    )

        new_status = "RETRY_CANCELLED" if status.startswith("RETRY_") else "CANCELLED"
        updates = {"status": new_status, "updated_at": _utc_now(), "exited_at": _utc_now(), "last_error": None}
        await db[COLLECTION].update_one_async({"_id": schedule_id}, {"$set": updates})
        doc.update(updates)
        await self._append_event(db, doc, "SCHEDULE_CANCELLED", new_status, f"Schedule cancelled ({new_status})")
        self._drop_runtime(str(schedule_id))
        return _serialize_schedule(doc)

    async def list_events(self, db, user_id: ObjectId, schedule_id: ObjectId) -> list[dict]:
        doc = await db[COLLECTION].find_one_async({"_id": schedule_id, "user_id": user_id})
        if not doc:
            raise ValueError("Scheduled trade not found")
        events = await db[EVENTS_COLLECTION].find_async({"schedule_id": schedule_id})
        events.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
        return [
            {
                "id": str(event.get("_id")),
                "event_type": event.get("event_type"),
                "status": event.get("status"),
                "message": event.get("message"),
                "payload": event.get("payload") or {},
                "created_at": _iso(event.get("created_at")),
            }
            for event in events
        ]

    async def hydrate_active(self, db, user_id: ObjectId, account: dict) -> None:
        docs = await db[COLLECTION].find_async(
            {
                "user_id": user_id,
                "account_id": account["_id"],
                "status": {"$in": list(ACTIVE_STATUSES)},
            }
        )
        for doc in docs:
            self._register_runtime(doc, seed_candles=[])

    async def handle_price(self, symbol: str, price: dict, *, db=None, account: Optional[dict] = None, user_id: Optional[str] = None) -> None:
        if db is None or account is None or not user_id:
            return
        broker_symbol = normalize_symbol(symbol)
        docs = await db[COLLECTION].find_async(
            {
                "user_id": ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id,
                "account_id": account["_id"],
                "symbol": {"$in": [broker_symbol, str(symbol or "").upper()]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            }
        )
        if not docs:
            return
        tick_price = _mid_from_price(price)
        if tick_price <= 0:
            return
        tick_time = self._resolve_tick_time(price)
        for doc in docs:
            lock = self._lock_for(str(doc["_id"]))
            async with lock:
                fresh = await db[COLLECTION].find_one_async({"_id": doc["_id"]})
                if not fresh or str(fresh.get("status") or "") not in ACTIVE_STATUSES:
                    continue
                try:
                    await self._process_schedule_tick(db, account, fresh, tick_price, tick_time)
                except Exception:
                    logger.exception("Scheduled trade tick failed | schedule=%s", doc.get("_id"))

    async def sync_linked_orders(self, db, user_oid: ObjectId, account: dict) -> None:
        docs = await db[COLLECTION].find_async(
            {
                "user_id": user_oid,
                "account_id": account["_id"],
                "status": {"$in": list(ORDER_TRACKING_STATUSES | {"STOP_EXIT"})},
            }
        )
        for doc in docs:
            lock = self._lock_for(str(doc["_id"]))
            async with lock:
                fresh = await db[COLLECTION].find_one_async({"_id": doc["_id"]})
                if not fresh:
                    continue
                try:
                    await self._sync_order_lifecycle(db, account, fresh)
                except Exception:
                    logger.exception("Scheduled trade order sync failed | schedule=%s", doc.get("_id"))

    async def notify_order_user_exit(self, db, order: dict) -> None:
        schedule_id = order.get("scheduled_trade_id")
        if not schedule_id:
            return
        doc = await db[COLLECTION].find_one_async({"_id": schedule_id})
        if not doc:
            return
        status = str(doc.get("status") or "")
        if status == "ORDER_FILLED":
            await self._set_status(db, doc, "USER_EXIT", "USER_EXIT", "Position closed by user")
        elif status == "RETRY_ORDER_FILLED":
            await self._set_status(db, doc, "RETRY_USER_EXIT", "RETRY_USER_EXIT", "Retry position closed by user")

    # --- internals ---

    def _lock_for(self, schedule_id: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        loop_locks = self._locks.get(loop)
        if loop_locks is None:
            loop_locks = {}
            self._locks[loop] = loop_locks
        lock = loop_locks.get(schedule_id)
        if lock is None:
            lock = asyncio.Lock()
            loop_locks[schedule_id] = lock
        return lock

    def _runtime_key(self, doc: dict) -> str:
        return f"{doc['user_id']}:{doc['account_id']}:{doc['_id']}"

    def _register_runtime(self, doc: dict, *, seed_candles: list[dict]) -> ScheduleRuntime:
        key = self._runtime_key(doc)
        runtime = ScheduleRuntime(
            schedule_id=doc["_id"],
            user_id=doc["user_id"],
            account_id=doc["account_id"],
            symbol=str(doc.get("symbol") or ""),
            timeframe=str(doc.get("timeframe") or "M5"),
        )
        if seed_candles:
            completed = []
            for candle in seed_candles:
                start = coerce_candle_time(candle.get("time") or candle.get("timestamp"))
                if start is None:
                    continue
                completed.append(
                    ExecCandle(
                        start=start.replace(tzinfo=None) if start.tzinfo else start,
                        open=float(candle.get("open") or 0),
                        high=float(candle.get("high") or 0),
                        low=float(candle.get("low") or 0),
                        close=float(candle.get("close") or 0),
                    )
                )
            if completed:
                # Seed forming bar from last candle; treat earlier as already completed.
                runtime.current = completed[-1]
                if len(completed) >= 2:
                    runtime.last_completed_start = completed[-2].start
        self._runtimes[key] = runtime
        symbol = normalize_symbol(runtime.symbol)
        self._symbol_index.setdefault(symbol, set()).add(key)
        return runtime

    def _drop_runtime(self, schedule_id: str) -> None:
        drop_keys = [key for key in self._runtimes if key.endswith(f":{schedule_id}")]
        for key in drop_keys:
            runtime = self._runtimes.pop(key, None)
            if runtime:
                symbol = normalize_symbol(runtime.symbol)
                bucket = self._symbol_index.get(symbol)
                if bucket is not None:
                    bucket.discard(key)
                    if not bucket:
                        self._symbol_index.pop(symbol, None)
            lock_id = str(runtime.schedule_id) if runtime else schedule_id
            for loop_locks in list(self._locks.values()):
                loop_locks.pop(lock_id, None)
                loop_locks.pop(schedule_id, None)

    def _get_runtime(self, doc: dict) -> ScheduleRuntime:
        key = self._runtime_key(doc)
        runtime = self._runtimes.get(key)
        if runtime is None:
            runtime = self._register_runtime(doc, seed_candles=[])
        return runtime

    @staticmethod
    def _resolve_tick_time(price: dict) -> datetime:
        raw = price.get("time") or price.get("brokerTime")
        if isinstance(raw, datetime):
            return raw.replace(tzinfo=None) if raw.tzinfo else raw
        if isinstance(raw, (int, float)):
            ts = float(raw)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
            except ValueError:
                pass
        return datetime.utcnow()

    async def _process_schedule_tick(self, db, account: dict, doc: dict, tick_price: float, tick_time: datetime) -> None:
        status = str(doc.get("status") or "")
        if status in ORDER_TRACKING_STATUSES or status == "STOP_EXIT":
            await self._sync_order_lifecycle(db, account, doc)
            # Refresh after sync; may have moved into RETRY_INITIATED for immediate place
            doc = await db[COLLECTION].find_one_async({"_id": doc["_id"]}) or doc
            status = str(doc.get("status") or "")

        if status == "RETRY_INITIATED":
            await self._place_retry_immediate(db, account, doc)
            return

        if status not in WATCHING_STATUSES:
            return

        runtime = self._get_runtime(doc)
        completed = self._roll_exec(runtime, tick_price, tick_time)
        if completed is None:
            return
        await self._on_bar_close(db, account, doc, completed.as_dict())

    def _roll_exec(self, runtime: ScheduleRuntime, price: float, tick_time: datetime) -> Optional[ExecCandle]:
        bar_start = _bar_start(tick_time, runtime.timeframe)
        if runtime.current is None:
            runtime.current = ExecCandle(start=bar_start, open=price, high=price, low=price, close=price)
            return None
        if runtime.current.start == bar_start:
            runtime.current.update(price)
            return None
        completed = runtime.current
        runtime.last_completed_start = completed.start
        runtime.current = ExecCandle(start=bar_start, open=price, high=price, low=price, close=price)
        return completed

    async def _on_bar_close(self, db, account: dict, doc: dict, candle: dict) -> None:
        status = str(doc.get("status") or "")
        side = str(doc.get("side") or "").upper()
        level = float(doc.get("level") or 0)
        symbol = str(doc.get("symbol") or "")
        pip_size = float(doc.get("pip_size") or scheduled_pip_size(symbol))

        if status == "INITIATED":
            if level_broken_on_close(side, candle, level):
                updates = {"status": "ARMED", "armed_at": _utc_now(), "updated_at": _utc_now(), "last_error": None}
                await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": updates})
                doc.update(updates)
                await self._append_event(
                    db,
                    doc,
                    "SCHEDULE_ARMED",
                    "ARMED",
                    f"{side} level broken on close {candle.get('close')} vs level {level}",
                    {"candle": candle, "level": level},
                )
            return

        if status == "ARMED":
            signal_ok = is_red(candle) if side == "SELL" else is_green(candle)
            if not signal_ok:
                return
            if is_oversized_signal_candle(
                candle,
                symbol,
                pip_size,
                max_pips=doc.get("max_signal_candle_pips"),
            ):
                await self._append_event(
                    db,
                    doc,
                    "SIGNAL_CANDLE_SKIPPED",
                    "ARMED",
                    "Signal candle oversized; waiting for next valid candle",
                    {
                        "candle": candle,
                        "max_signal_candle_pips": doc.get("max_signal_candle_pips"),
                    },
                )
                return
            await self._place_primary(db, account, doc, candle)
            return

        if status == "RETRY_ARMED":
            # Reserved for future candle re-arm; v1 does not use this path.
            return

    async def _place_primary(self, db, account: dict, doc: dict, candle: dict) -> None:
        side = str(doc.get("side") or "").upper()
        point = float(doc.get("point_size") or 0.01)
        digits = int(doc.get("price_digits") or 5)
        entry, stop_loss = entry_sl_for_side(side, candle, point)
        entry = normalize_price_to_symbol(entry, {"digits": digits, "point": point})
        stop_loss = normalize_price_to_symbol(stop_loss, {"digits": digits, "point": point})
        target = usable_target(side, entry, stop_loss, doc.get("target"))

        try:
            symbol_spec = await metaapi_service.get_symbol_specification(
                account["api_token"],
                account["account_id"],
                doc["symbol"],
            )
            digits = digits_from_symbol_spec(symbol_spec)
            detected_point = point_size_from_symbol_spec(symbol_spec)
            if detected_point > 0:
                point = detected_point
                entry, stop_loss = entry_sl_for_side(side, candle, point)
                entry = normalize_price_to_symbol(entry, {"digits": digits, "point": point})
                stop_loss = normalize_price_to_symbol(stop_loss, {"digits": digits, "point": point})
                target = usable_target(side, entry, stop_loss, doc.get("target"))
        except Exception:
            symbol_spec = {"symbol": doc["symbol"], "digits": digits, "point": point}

        try:
            risk_ctx = await metaapi_service.get_risk_context(
                account["api_token"],
                account["account_id"],
                doc["symbol"],
            )
        except Exception:
            risk_ctx = None

        quantity = quantity_from_risk(
            float(doc.get("risk_amount") or 0),
            entry,
            stop_loss,
            symbol_spec=symbol_spec,
            live_ctx=risk_ctx,
            symbol=str(doc.get("symbol") or ""),
            account_currency=str(account.get("account_currency") or "USD"),
        )
        if quantity <= 0:
            await self._set_error(db, doc, "Risk amount is too small for broker minimum volume.")
            return

        order_doc = await self._insert_order_doc(
            db,
            account,
            doc,
            entry=entry,
            stop_loss=stop_loss,
            quantity=quantity,
            target=target,
            is_retry=False,
        )
        placement_payload = {
            "symbol": doc["symbol"],
            "order_type": "SL",
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "quantity": quantity,
        }
        try:
            placement = await place_pending_order_with_limit_fallback(
                metaapi_service,
                account["api_token"],
                account["account_id"],
                placement_payload,
            )
        except Exception as exc:
            failure = str(exc)
            await db.orders.update_one_async(
                {"_id": order_doc["_id"]},
                {"$set": {"status": "FAILED", "failure_reason": failure, "updated_at": _utc_now()}},
            )
            await self._set_error(db, doc, failure)
            await self._append_event(db, doc, "ORDER_PLACEMENT_FAILED", doc.get("status"), failure)
            return

        result = placement.get("result") or {}
        fallback = placement.get("fallback")
        meta_order_id = str(result.get("orderId") or result.get("id") or "")
        placed_type = str(placement.get("order_type") or "SL").upper()
        order_updates = {
            "meta_order_id": meta_order_id,
            "status": "PENDING",
            "failure_reason": None,
            **order_placement_fallback_fields(fallback),
            "updated_at": _utc_now(),
        }
        await db.orders.update_one_async({"_id": order_doc["_id"]}, {"$set": order_updates})
        if fallback:
            self._save_order_event(
                db,
                doc["user_id"],
                order_doc["_id"],
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                sl_limit_fallback_event_message(doc["symbol"], str(fallback.get("sl_placement_error") or ""), source=order_doc),
                merge_order_log_payload(fallback, source=order_doc),
                symbol=doc["symbol"],
                broker_info=doc.get("broker_info"),
                placement_fallback_reason=fallback.get("fallback_reason"),
            )

        schedule_updates = {
            "status": "ORDER_PLACED",
            "entry": entry,
            "stop_loss": stop_loss,
            "quantity": quantity,
            "point_size": point,
            "price_digits": digits,
            "signal_candle": {
                "time": _iso(candle.get("time")),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
            },
            "order_id": order_doc["_id"],
            "meta_order_id": meta_order_id,
            "placement_order_type": placed_type,
            "placement_fallback_reason": (fallback or {}).get("fallback_reason"),
            "placed_at": _utc_now(),
            "updated_at": _utc_now(),
            "last_error": None,
        }
        await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": schedule_updates})
        doc.update(schedule_updates)
        await self._append_event(
            db,
            doc,
            "ORDER_PLACED",
            "ORDER_PLACED",
            f"Primary {placed_type} placed @ {entry} SL {stop_loss}",
            {"order_id": str(order_doc["_id"]), "order_type": placed_type, "fallback": fallback},
        )

    async def _place_retry_immediate(self, db, account: dict, doc: dict) -> None:
        entry = doc.get("entry")
        stop_loss = doc.get("stop_loss")
        quantity = doc.get("quantity")
        if entry is None or stop_loss is None or quantity is None:
            await self._set_error(db, doc, "Retry missing entry/stop/quantity from primary leg")
            return
        side = str(doc.get("side") or "").upper()
        target = usable_target(side, float(entry), float(stop_loss), doc.get("target"))
        order_doc = await self._insert_order_doc(
            db,
            account,
            doc,
            entry=float(entry),
            stop_loss=float(stop_loss),
            quantity=float(quantity),
            target=target,
            is_retry=True,
        )
        placement_payload = {
            "symbol": doc["symbol"],
            "order_type": "SL",
            "side": side,
            "entry": float(entry),
            "stop_loss": float(stop_loss),
            "target": target,
            "quantity": float(quantity),
        }
        try:
            result = await metaapi_service.place_pending_order(
                account["api_token"],
                account["account_id"],
                placement_payload,
            )
        except Exception as exc:
            failure = str(exc)
            # Explicitly no LIMIT fallback on retry
            note = failure
            if is_invalid_price_error(exc):
                note = f"{failure} (retry SL-only; LIMIT fallback disabled)"
            await db.orders.update_one_async(
                {"_id": order_doc["_id"]},
                {"$set": {"status": "FAILED", "failure_reason": note, "updated_at": _utc_now()}},
            )
            await self._set_error(db, doc, note)
            await self._append_event(db, doc, "RETRY_ORDER_PLACEMENT_FAILED", "RETRY_INITIATED", note)
            return

        meta_order_id = str(result.get("orderId") or result.get("id") or "")
        await db.orders.update_one_async(
            {"_id": order_doc["_id"]},
            {"$set": {"meta_order_id": meta_order_id, "status": "PENDING", "failure_reason": None, "updated_at": _utc_now()}},
        )
        updates = {
            "status": "RETRY_ORDER_PLACED",
            "retry_order_id": order_doc["_id"],
            "retry_meta_order_id": meta_order_id,
            "placement_order_type": "SL",
            "updated_at": _utc_now(),
            "placed_at": _utc_now(),
            "last_error": None,
        }
        await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": updates})
        doc.update(updates)
        await self._append_event(
            db,
            doc,
            "RETRY_ORDER_PLACED",
            "RETRY_ORDER_PLACED",
            f"Retry SL placed @ {entry} SL {stop_loss}",
            {"order_id": str(order_doc["_id"])},
        )

    async def _insert_order_doc(
        self,
        db,
        account: dict,
        schedule: dict,
        *,
        entry: float,
        stop_loss: float,
        quantity: float,
        target: Optional[float],
        is_retry: bool,
    ) -> dict:
        side = str(schedule.get("side") or "").upper()
        now = _utc_now()
        order_doc = {
            "user_id": schedule["user_id"],
            "account_id": account["_id"],
            "symbol": schedule.get("symbol"),
            "order_type": "SL",
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "comment": "Scheduled break retry" if is_retry else "Scheduled break trade",
            "quantity": quantity,
            "risk_amount": schedule.get("risk_amount"),
            "rr_ratio": calc_rr(side, entry, stop_loss, target) if target is not None else None,
            "meta_order_id": None,
            "status": "PLACEMENT_PENDING",
            "failure_reason": None,
            "scheduled_trade_id": schedule["_id"],
            "created_at": now,
            "updated_at": now,
            "opened_at": now,
            "closed_at": None,
            "last_broker_seen_at": None,
            "is_open_position": False,
            "position_quantity": None,
            "realized_pl": None,
            "unrealized_pl": None,
            "broker_info": schedule.get("broker_info") or _broker_info_from_account(account),
            "manual_context": {
                "retryable_order": False,
                "automatic_trade_management": False,
                "retry_used": False,
                "partial_booked_4r": False,
                "target_booked": False,
                "position_was_open": False,
                "parent_order_id": str(schedule.get("order_id")) if is_retry and schedule.get("order_id") else None,
                "is_retry_child": bool(is_retry),
                "is_scheduled_retry": bool(is_retry),
                "scheduled_trade": True,
            },
        }
        result = await db.orders.insert_one_async(order_doc)
        order_doc["_id"] = result.inserted_id
        self._save_order_event(
            db,
            schedule["user_id"],
            order_doc["_id"],
            "ORDER_CREATE_REQUESTED",
            "PLACEMENT_PENDING",
            append_order_log_prices(
                f"{order_doc['symbol']} scheduled {'retry ' if is_retry else ''}order create requested",
                order_doc,
            ),
            merge_order_log_payload({"scheduled_trade_id": str(schedule["_id"])}, source=order_doc),
            symbol=order_doc["symbol"],
            broker_info=order_doc.get("broker_info"),
            notify_user=False,
        )
        return order_doc

    async def _sync_order_lifecycle(self, db, account: dict, doc: dict) -> None:
        status = str(doc.get("status") or "")
        is_retry_leg = status.startswith("RETRY_")
        order_id = doc.get("retry_order_id") if is_retry_leg else doc.get("order_id")
        if not order_id and status == "STOP_EXIT":
            # Primary stop already recorded; maybe start retry
            await self._maybe_start_retry(db, doc)
            return
        if not order_id:
            return
        order = await db.orders.find_one_async({"_id": order_id})
        if not order:
            return
        order_status = str(order.get("status") or "").upper()

        if status in {"ORDER_PLACED", "RETRY_ORDER_PLACED"} and order_status in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}:
            next_status = "RETRY_ORDER_FILLED" if is_retry_leg else "ORDER_FILLED"
            updates = {"status": next_status, "filled_at": _utc_now(), "updated_at": _utc_now(), "last_error": None}
            if order.get("meta_position_id"):
                updates["meta_position_id"] = order.get("meta_position_id")
            await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": updates})
            doc.update(updates)
            await self._append_event(db, doc, next_status, next_status, f"Linked order filled ({order_status})")
            return

        if status in {"ORDER_PLACED", "RETRY_ORDER_PLACED"} and order_status == "CANCELLED":
            next_status = "RETRY_CANCELLED" if is_retry_leg else "CANCELLED"
            await self._set_status(db, doc, next_status, "ORDER_CANCELLED", "Linked pending order cancelled")
            self._drop_runtime(str(doc["_id"]))
            return

        if status in {"ORDER_FILLED", "RETRY_ORDER_FILLED", "ORDER_PLACED", "RETRY_ORDER_PLACED"} and order_status == "CLOSED":
            exit_status = self._classify_exit(order, is_retry_leg=is_retry_leg)
            await self._set_status(db, doc, exit_status, exit_status, f"Linked order closed → {exit_status}")
            if exit_status == "STOP_EXIT":
                await self._maybe_start_retry(db, {**doc, "status": exit_status})
            else:
                self._drop_runtime(str(doc["_id"]))
            return

        if status == "STOP_EXIT":
            await self._maybe_start_retry(db, doc)

    def _classify_exit(self, order: dict, *, is_retry_leg: bool) -> str:
        context = order.get("manual_context") or {}
        if context.get("target_booked"):
            return "RETRY_TARGET_EXIT" if is_retry_leg else "TARGET_EXIT"
        # Clean stop heuristic: never booked target/partial and non-positive realized PL
        if context.get("partial_booked_4r"):
            return "RETRY_USER_EXIT" if is_retry_leg else "USER_EXIT"
        realized = order.get("realized_pl")
        try:
            realized_f = float(realized) if realized is not None else None
        except (TypeError, ValueError):
            realized_f = None
        if realized_f is not None and realized_f > PRICE_EPSILON:
            # Likely target / profitable user exit without target_booked flag
            target = order.get("target")
            if target is not None:
                return "RETRY_TARGET_EXIT" if is_retry_leg else "TARGET_EXIT"
            return "RETRY_USER_EXIT" if is_retry_leg else "USER_EXIT"
        if context.get("position_was_open") or order.get("is_open_position") is False:
            # Prefer stop when lossy or flat
            if realized_f is None or realized_f <= PRICE_EPSILON:
                return "RETRY_STOP_EXIT" if is_retry_leg else "STOP_EXIT"
        return "RETRY_USER_EXIT" if is_retry_leg else "USER_EXIT"

    async def _maybe_start_retry(self, db, doc: dict) -> None:
        if str(doc.get("status") or "") != "STOP_EXIT":
            return
        if not doc.get("retryable_order") or doc.get("retry_used"):
            self._drop_runtime(str(doc["_id"]))
            return
        claimed = await db[COLLECTION].find_one_and_update_async(
            {"_id": doc["_id"], "status": "STOP_EXIT", "retry_used": False, "retryable_order": True},
            {"$set": {"retry_used": True, "status": "RETRY_INITIATED", "updated_at": _utc_now(), "last_error": None}},
        )
        if not claimed:
            self._drop_runtime(str(doc["_id"]))
            return
        claimed["status"] = "RETRY_INITIATED"
        claimed["retry_used"] = True
        await self._append_event(
            db,
            claimed,
            "RETRY_INITIATED",
            "RETRY_INITIATED",
            "Primary stop-out; placing same SL once (retry)",
        )
        # Immediate place is handled on next tick / call site
        account = await db.meta_accounts.find_one_async({"_id": claimed["account_id"]})
        if account:
            await self._place_retry_immediate(db, account, claimed)

    async def _set_status(self, db, doc: dict, status: str, event_type: str, message: str) -> None:
        updates = {"status": status, "updated_at": _utc_now(), "last_error": None}
        if status in {
            "TARGET_EXIT",
            "STOP_EXIT",
            "USER_EXIT",
            "CANCELLED",
            "RETRY_TARGET_EXIT",
            "RETRY_STOP_EXIT",
            "RETRY_USER_EXIT",
            "RETRY_CANCELLED",
        }:
            updates["exited_at"] = _utc_now()
        await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": updates})
        doc.update(updates)
        await self._append_event(db, doc, event_type, status, message)

    async def _set_error(self, db, doc: dict, message: str) -> None:
        updates = {"last_error": message, "updated_at": _utc_now()}
        await db[COLLECTION].update_one_async({"_id": doc["_id"]}, {"$set": updates})
        doc.update(updates)
        await self._append_event(db, doc, "SCHEDULE_ERROR", doc.get("status"), message)

    async def _append_event(self, db, doc: dict, event_type: str, status: str, message: str, payload: Optional[dict] = None) -> None:
        await db[EVENTS_COLLECTION].insert_one_async(
            {
                "schedule_id": doc["_id"],
                "user_id": doc.get("user_id"),
                "event_type": event_type,
                "status": status,
                "message": message,
                "payload": payload or {},
                "created_at": _utc_now(),
            }
        )

    @staticmethod
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
    ) -> None:
        db.order_events.insert_one(
            {
                "order_id": order_id,
                "event_type": event_type,
                "status": status,
                "message": message,
                "event_ts_ist": metaapi_service.now_ist(),
                "payload": payload or {},
                "created_at": _utc_now(),
                "symbol": symbol,
                "broker_info": broker_info or {},
                "failure_reason": failure_reason,
                "placement_fallback_reason": placement_fallback_reason,
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
                    "created_at": _utc_now(),
                    "broker_info": broker_info or {},
                }
            )


async def seed_recent_candles(db, account: dict, broker_symbol: str, timeframe: str, limit: int = 30) -> list[dict]:
    tf = normalize_scheduled_timeframe(timeframe)
    seconds = int(TIMEFRAME_SECONDS[normalize_timeframe(tf)])
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(seconds=seconds * max(limit, 5))
    try:
        return await get_chart_candles(db, account, broker_symbol, tf, from_time, to_time, limit)
    except Exception:
        logger.exception("Failed to seed scheduled trade candles | symbol=%s tf=%s", broker_symbol, tf)
        return []


scheduled_trade_manager = ScheduledTradeManager.instance()
