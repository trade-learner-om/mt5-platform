import asyncio
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from bson import ObjectId
from fastapi import WebSocket
from pymongo import DESCENDING
from zoneinfo import ZoneInfo

from ..config import settings
from .async_runtime import run_coro_in_thread, run_sync
from .indian_market_stream import indian_market_stream_manager, INDIAN_WATCHLIST_COLLECTION
from .market_data_stream import market_data_stream
from .symbol_resolver import lookup_live_price


class LiveStateHub:
    def __init__(self):
        self._user_sockets = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, session_id: str, ws: WebSocket):
        async with self._lock:
            self._user_sockets[user_id][ws] = session_id

    async def disconnect(self, user_id: str, ws: WebSocket):
        async with self._lock:
            if ws in self._user_sockets[user_id]:
                self._user_sockets[user_id].pop(ws, None)

    async def push_snapshot(self, db, user_id: str, schedule_reconcile: bool = True):
        user_oid = ObjectId(user_id)
        user = await db.users.find_one_async(
            {"_id": user_oid},
            {"is_admin": 1, "selected_account_id": 1, "selected_indian_account_id": 1},
        )
        today_start_utc, today_end_utc = _today_utc_range()
        if schedule_reconcile:
            async def resync_snapshot(db_arg, user_id_arg):
                await self.push_snapshot(db_arg, user_id_arg, schedule_reconcile=False)

            market_data_stream.schedule_background_reconcile(
                db, user_id, resync_snapshot, include_all_accounts=True
            )
        orders = await db.orders.find_async(
            {
                "user_id": user_oid,
                "dry_run": {"$ne": True},
                "$or": [
                    {"status": {"$in": ["WAITING_TRIGGER", "PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]}},
                    {
                        "created_at": {
                            "$gte": today_start_utc,
                            "$lt": today_end_utc,
                        },
                    },
                ],
            },
        )
        orders.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
        orders = orders[:100]
        orders = await run_coro_in_thread(market_data_stream.enrich_orders_pl, db, user_oid, orders)
        watchlist_items = await db.watchlist_items.find_async({"user_id": user_oid})
        indian_watchlist_query = {"user_id": user_oid}
        if user and user.get("selected_indian_account_id"):
            indian_watchlist_query["account_id"] = user["selected_indian_account_id"]
        indian_watchlist_items = await db[INDIAN_WATCHLIST_COLLECTION].find_async(indian_watchlist_query)
        live_prices = market_data_stream.get_prices(user_id)
        notifications = await db.notifications.find_async({"user_id": user_oid})
        notifications.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
        notifications = notifications[:200]
        scheduled_trades = await db.scheduled_trades.find_async({"user_id": user_oid})
        scheduled_trades.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
        scheduled_trades = scheduled_trades[:100]
        indian_market = await run_sync(indian_market_stream_manager.build_market_overview, user_id)
        invalid_watchlist_symbols = market_data_stream.get_invalid_watchlist_symbols(user_id)
        payload = {
            "prices": {
                symbol: {
                    "symbol": symbol,
                    "bid": tick.get("bid"),
                    "ask": tick.get("ask"),
                    "price": _current_price(tick),
                    "price_digits": tick.get("price_digits"),
                    "time": _iso_timestamp(tick.get("time")),
                }
                for symbol, tick in live_prices.items()
            },
            "watchlist": [
                {
                    "symbol": item["symbol"],
                    "bid": lookup_live_price(live_prices, item["symbol"]).get("bid"),
                    "ask": lookup_live_price(live_prices, item["symbol"]).get("ask"),
                    "price": _current_price(lookup_live_price(live_prices, item["symbol"])),
                    "price_digits": lookup_live_price(live_prices, item["symbol"]).get("price_digits"),
                    "time": _iso_timestamp(lookup_live_price(live_prices, item["symbol"]).get("time")),
                }
                for item in watchlist_items
                if item["symbol"] not in invalid_watchlist_symbols
            ],
            "indian_market": {
                **indian_market,
                "watchlist": [
                    {
                        "symbol": item["symbol"],
                        "display_name": item.get("display_name") or item["symbol"],
                        "exchange": item.get("exchange"),
                        "instrument_token": item.get("instrument_token"),
                        "price": next((row.get("price") for row in indian_market.get("watchlist", []) if row.get("symbol") == item["symbol"]), None),
                        "change": next((row.get("change") for row in indian_market.get("watchlist", []) if row.get("symbol") == item["symbol"]), None),
                        "time": next((row.get("time") for row in indian_market.get("watchlist", []) if row.get("symbol") == item["symbol"]), None),
                    }
                    for item in indian_watchlist_items
                ],
            },
            "orders": [
                {
                    "id": str(o["_id"]),
                    "symbol": o.get("symbol"),
                    "status": o.get("status"),
                    "order_type": o.get("order_type"),
                    "side": o.get("side"),
                    "quantity": o.get("quantity"),
                    "entry": o.get("entry"),
                    "stop_loss": o.get("stop_loss"),
                    "target": o.get("target"),
                    "rr_ratio": o.get("rr_ratio"),
                    "is_open_position": o.get("is_open_position"),
                    "position_quantity": o.get("position_quantity"),
                    "realized_pl": o.get("realized_pl"),
                    "unrealized_pl": o.get("unrealized_pl"),
                    "failure_reason": o.get("failure_reason"),
                    "placement_fallback_reason": o.get("placement_fallback_reason"),
                    "comment": o.get("comment"),
                    "manual_context": o.get("manual_context") or {},
                    "broker_info": o.get("broker_info"),
                    "account_id": str(o.get("account_id") or "") or None,
                    "copy_group_id": o.get("copy_group_id"),
                    "planner_plan_id": ((o.get("planner_context") or {}).get("plan_id")),
                    "planner_plan_account_id": ((o.get("planner_context") or {}).get("plan_account_id")),
                    "planner_targets": ((o.get("planner_context") or {}).get("targets") or []),
                    "meta_order_id": str(o.get("meta_order_id")) if o.get("meta_order_id") else None,
                    "meta_position_id": str(o.get("meta_position_id")) if o.get("meta_position_id") else None,
                    "external_source": o.get("external_source"),
                    "opened_at": _iso_timestamp(o.get("opened_at")),
                    "closed_at": _iso_timestamp(o.get("closed_at")),
                    "last_broker_seen_at": _iso_timestamp(o.get("last_broker_seen_at")),
                    "created_at": _iso_timestamp(o.get("created_at")),
                    "updated_at": _iso_timestamp(o.get("updated_at")),
                }
                for o in orders
            ],
            "notifications": [
                {
                    "id": str(notification["_id"]),
                    "order_id": str(notification["order_id"]) if notification.get("order_id") else None,
                    "symbol": notification.get("symbol"),
                    "category": notification.get("category", "orders"),
                    "event_type": notification.get("event_type"),
                    "status": notification.get("status"),
                    "activity": notification.get("activity", ""),
                    "failure_reason": notification.get("failure_reason"),
                    "timestamp": _iso_timestamp(notification.get("created_at")),
                    "broker_info": notification.get("broker_info"),
                }
                for notification in notifications
            ],
            "scheduled_trades": [
                {
                    "id": str(item["_id"]),
                    "account_id": str(item.get("account_id") or "") or None,
                    "symbol": item.get("symbol"),
                    "timeframe": item.get("timeframe"),
                    "level": item.get("level"),
                    "side": item.get("side"),
                    "risk_amount": item.get("risk_amount"),
                    "target": item.get("target"),
                    "retryable_order": bool(item.get("retryable_order")),
                    "retry_used": bool(item.get("retry_used")),
                    "status": item.get("status"),
                    "entry": item.get("entry"),
                    "stop_loss": item.get("stop_loss"),
                    "quantity": item.get("quantity"),
                    "order_id": str(item["order_id"]) if item.get("order_id") else None,
                    "retry_order_id": str(item["retry_order_id"]) if item.get("retry_order_id") else None,
                    "placement_fallback_reason": item.get("placement_fallback_reason"),
                    "placement_order_type": item.get("placement_order_type"),
                    "last_error": item.get("last_error"),
                    "broker_info": item.get("broker_info") or {},
                    "created_at": _iso_timestamp(item.get("created_at")),
                    "updated_at": _iso_timestamp(item.get("updated_at")),
                    "armed_at": _iso_timestamp(item.get("armed_at")),
                    "placed_at": _iso_timestamp(item.get("placed_at")),
                    "filled_at": _iso_timestamp(item.get("filled_at")),
                    "exited_at": _iso_timestamp(item.get("exited_at")),
                }
                for item in scheduled_trades
            ],
        }

        message = json.dumps(_json_safe(payload))
        dead = []
        for ws in list(self._user_sockets[user_id].keys()):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._user_sockets[user_id].pop(ws, None)

    async def force_logout_user_sessions(self, user_id: str, except_session_id: Optional[str] = None):
        sockets = []
        async with self._lock:
            for ws, session_id in list(self._user_sockets[user_id].items()):
                if except_session_id and session_id == except_session_id:
                    continue
                sockets.append(ws)
                self._user_sockets[user_id].pop(ws, None)

        for ws in sockets:
            try:
                await ws.send_text(json.dumps({"type": "force_logout", "reason": "Signed in on another device"}))
            except Exception:
                pass
            try:
                await ws.close(code=1008)
            except Exception:
                pass


live_state_hub = LiveStateHub()


def _iso_timestamp(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _json_safe(value):
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=str)]
    return value


def _today_utc_range():
    now_local = datetime.now(ZoneInfo(settings.timezone))
    local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _current_price(price_tick: dict) -> Optional[float]:
    bid = price_tick.get("bid")
    ask = price_tick.get("ask")
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    bid_decimal = Decimal(str(bid))
    ask_decimal = Decimal(str(ask))
    digits = price_tick.get("price_digits")
    if digits is not None:
        try:
            precision = max(0, min(int(digits), 10))
        except (TypeError, ValueError):
            precision = max(-bid_decimal.as_tuple().exponent, -ask_decimal.as_tuple().exponent, 0)
    else:
        precision = max(-bid_decimal.as_tuple().exponent, -ask_decimal.as_tuple().exponent, 0)
    midpoint = (bid_decimal + ask_decimal) / Decimal("2")
    return float(midpoint.quantize(Decimal(1).scaleb(-precision)))
