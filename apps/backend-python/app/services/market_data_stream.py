import asyncio
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional
from weakref import WeakKeyDictionary

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import AutoReconnect, PyMongoError, ServerSelectionTimeoutError
try:
    from metaapi_cloud_sdk.clients.timeout_exception import TimeoutException
except ImportError:  # Local MT5 runtime does not depend on MetaApi.
    class TimeoutException(Exception):
        pass

from .metaapi_client import (
    is_missing_broker_order_error,
    merge_realized_pl_on_close,
    metaapi_service,
    needs_active_booked_pl_resolution,
    needs_closed_realized_pl_resolution,
)
from .async_runtime import run_coro_in_thread, run_sync
from .manual_order_runtime import manual_order_runtime_manager
from .m1_candle_builder import m1_candle_builder
from .risk import digits_from_symbol_spec, normalize_price_to_symbol
from .symbol_resolver import normalize_symbol, resolve_broker_symbol
from .master_break_runtime import master_break_manager
from .scheduled_trade_runtime import scheduled_trade_manager
from .trap_reversal_automation import trap_reversal_manager
from .trade_planner_runtime import trade_planner_runtime_manager

logger = logging.getLogger(__name__)
TRADE_PLAN_COLLECTION = "trade_plans"
BROKER_MISSING_CONFIRMATION_SECONDS = 20
ORDER_RECONCILE_INTERVAL_SECONDS = 2
BACKGROUND_RECONCILE_INTERVAL_SECONDS = 8
SNAPSHOT_DEBOUNCE_SECONDS = 0.5
MONGO_OUTAGE_BACKOFF_SECONDS = 10
STREAM_REFRESH_DEBOUNCE_SECONDS = 25


def _is_mongo_unavailable_error(exc: Exception) -> bool:
    if isinstance(exc, (ServerSelectionTimeoutError, AutoReconnect)):
        return True
    return isinstance(exc, PyMongoError) and "localhost:27017" in str(exc)


def _load_primary_stream_symbol_groups(db, user_oid: ObjectId, account_db_id) -> dict[str, set[str]]:
    watchlist_symbols = {
        str(item.get("symbol") or "").upper()
        for item in db.watchlist_items.find({"user_id": user_oid})
        if str(item.get("symbol") or "").strip()
    }
    planner_symbols = {
        str(item.get("symbol") or "").upper()
        for item in db[TRADE_PLAN_COLLECTION].find(
            {
                "user_id": user_oid,
                "status": {"$ne": "INACTIVE"},
                "$or": [
                    {"account_targets.account_id": account_db_id},
                    {"account_id": account_db_id},
                ],
            },
            {"symbol": 1},
        )
        if str(item.get("symbol") or "").strip()
    }
    active_trade_symbols = {
        str(item.get("symbol") or "").upper()
        for item in db.orders.find(
            {
                "user_id": user_oid,
                "account_id": account_db_id,
                "dry_run": {"$ne": True},
                "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
            },
            {"symbol": 1},
        )
        if str(item.get("symbol") or "").strip()
    }
    return {
        "watchlist_symbols": watchlist_symbols,
        "planner_symbols": planner_symbols,
        "active_trade_symbols": active_trade_symbols,
    }


def _restore_running_user_ids(db) -> set[str]:
    user_ids = set()
    user_ids.update(
        str(doc["user_id"])
        for doc in db[TRADE_PLAN_COLLECTION].find(
            {"auto_execution_enabled": True, "status": "RUNNING"},
            {"user_id": 1},
        )
    )
    user_ids.update(
        str(doc["user_id"])
        for doc in db["master_break_runs"].find(
            {"status": "RUNNING"},
            {"user_id": 1},
        )
        if doc.get("user_id") is not None
    )
    return user_ids


def _users_for_unseeded_tick(db, account_filter: str | None) -> list[dict]:
    users = []
    user_query = {"selected_account_id": {"$exists": True}}
    for user in db.users.find(user_query, {"_id": 1, "selected_account_id": 1}):
        account = db.meta_accounts.find_one({"_id": user.get("selected_account_id"), "user_id": user["_id"]})
        if not account or str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
            continue
        if account_filter and str(account.get("account_id") or "") != account_filter and str(account.get("_id") or "") != account_filter:
            continue
        users.append({"user_id": str(user["_id"])})
    return users


class _MetaPriceListener:
    def __init__(self, manager, session_key: str):
        self.manager = manager
        self.session_key = session_key

    async def on_symbol_price_updated(self, *args):
        price = args[-1] if args else None
        if isinstance(price, dict):
            await self.manager.handle_price(self.session_key, price)

    async def on_symbol_prices_updated(self, *args):
        prices = args[-1] if args else []
        if isinstance(prices, list):
            for price in prices:
                if isinstance(price, dict):
                    await self.manager.handle_price(self.session_key, price)

    async def on_broker_connection_status_changed(self, *args):
        logger.info("Broker connection status changed | session=%s payload=%s", self.session_key, args[-1] if args else None)

    async def on_health_status(self, *args):
        logger.info("Health status update | session=%s payload=%s", self.session_key, args[-1] if args else None)

    def __getattr__(self, item):
        """
        MetaApi synchronization listener may invoke many callback names.
        Treat unknown callbacks as no-ops so stream does not crash.
        """
        if item.startswith("on_"):
            async def _noop(*args, **kwargs):
                return None
            return _noop
        raise AttributeError(item)


class MarketDataStreamManager:
    def __init__(self):
        self._tick_loop = asyncio.new_event_loop()
        self._tick_loop_thread = threading.Thread(
            target=self._run_tick_loop,
            name="market-data-tick-loop",
            daemon=True,
        )
        self._tick_loop_thread.start()
        self._sessions = {}
        self._price_cache = defaultdict(dict)
        self._extra_symbols = defaultdict(set)
        self._blocked_reasons = {}
        self._invalid_watchlist_symbols = defaultdict(set)
        self._pending_prices = defaultdict(deque)
        self._tick_tasks = {}
        self._snapshot_tasks = {}
        self._last_reconcile_at = {}
        self._last_direct_reconcile_at = {}
        self._last_price_tick_at = {}
        self._mongo_outage_until = {}
        self._tick_locks = {}
        self._stream_ensure_locks: WeakKeyDictionary = WeakKeyDictionary()
        self._background_reconcile_tasks = {}
        self._background_reconcile_inflight = set()
        self._last_stream_refresh_at = {}

    def stream_refresh_is_debounced(self, user_id: str) -> bool:
        last = self._last_stream_refresh_at.get(user_id)
        if not last:
            return False
        return (datetime.now(timezone.utc) - last).total_seconds() < STREAM_REFRESH_DEBOUNCE_SECONDS

    def mark_stream_refreshed(self, user_id: str) -> None:
        self._last_stream_refresh_at[user_id] = datetime.now(timezone.utc)

    def _primary_session_for_account(self, user_id: str, account_db_id) -> Optional[dict]:
        primary = self._sessions.get(user_id)
        if not primary or primary.get("kind") != "primary":
            return None
        if str(primary.get("account_db_id") or "") != str(account_db_id):
            return None
        return primary

    def _primary_symbols_cover(self, user_id: str, account_db_id, symbols: set[str]) -> bool:
        primary = self._primary_session_for_account(user_id, account_db_id)
        if not primary:
            return False
        primary_symbols = {normalize_symbol(symbol) for symbol in (primary.get("symbols") or [])}
        required_symbols = {normalize_symbol(symbol) for symbol in symbols if str(symbol or "").strip()}
        return required_symbols.issubset(primary_symbols)

    def _run_tick_loop(self) -> None:
        asyncio.set_event_loop(self._tick_loop)
        self._tick_loop.run_forever()

    async def _run_on_tick_loop(self, factory, /, *args, **kwargs):
        current_loop = asyncio.get_running_loop()
        if current_loop is self._tick_loop:
            return await factory(*args, **kwargs)
        future = asyncio.run_coroutine_threadsafe(factory(*args, **kwargs), self._tick_loop)
        return await asyncio.wrap_future(future)

    def _cancel_task_threadsafe(self, task: asyncio.Task | None) -> None:
        if not task or task.done():
            return
        task_loop = task.get_loop()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is task_loop:
            task.cancel()
            return
        task_loop.call_soon_threadsafe(task.cancel)

    def get_prices(self, user_id: str) -> dict:
        return self._price_cache.get(user_id, {})

    def get_invalid_watchlist_symbols(self, user_id: str) -> set[str]:
        return set(self._invalid_watchlist_symbols.get(user_id, set()))

    def _user_stream_lock(self, user_id: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        loop_locks = self._stream_ensure_locks.get(loop)
        if loop_locks is None:
            loop_locks = {}
            self._stream_ensure_locks[loop] = loop_locks
        lock = loop_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            loop_locks[user_id] = lock
        return lock

    async def ensure_user_stream(self, db, user_id: str, on_update):
        async with self._user_stream_lock(user_id):
            await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=True)
            await self._ensure_execution_streams(db, user_id, on_update, retry_on_timeout=True)

    async def refresh_live_stream(self, db, user_id: str, on_update, *, force: bool = False) -> None:
        async with self._user_stream_lock(user_id):
            primary = self._sessions.get(user_id)
            needs_setup = not primary or primary.get("kind") != "primary"
            stale_primary = False
            if primary and primary.get("kind") == "primary":
                last_tick = self._last_price_tick_at.get(user_id)
                started_at = primary.get("started_at")
                now = datetime.now(timezone.utc)
                stale_seconds = None
                if last_tick:
                    stale_seconds = (now - last_tick).total_seconds()
                elif started_at and primary.get("symbols"):
                    stale_seconds = (now - started_at).total_seconds()
                stale_primary = stale_seconds is not None and stale_seconds > 45

            # New strategy symbols (e.g. Trend Pilot close-mode) must be subscribed even when
            # the primary session already looks healthy on other instruments.
            uncovered_strategy_symbols = False
            if primary and primary.get("kind") == "primary" and not needs_setup and not stale_primary:
                required = set(trap_reversal_manager.active_symbols(str(user_id), None) or set())
                required |= set(master_break_manager.active_symbols(str(user_id), None) or set())
                required |= set(scheduled_trade_manager.active_symbols(str(user_id), None) or set())
                try:
                    user_oid = ObjectId(user_id)
                    required |= set(scheduled_trade_manager.active_symbols_from_db(db, user_oid, None) or set())
                except Exception:
                    pass
                primary_symbols = {normalize_symbol(symbol) for symbol in (primary.get("symbols") or [])}
                uncovered_strategy_symbols = bool(
                    {normalize_symbol(symbol) for symbol in required if str(symbol or "").strip()} - primary_symbols
                )

            if (
                not force
                and not needs_setup
                and not stale_primary
                and not uncovered_strategy_symbols
                and self.stream_refresh_is_debounced(user_id)
            ):
                logger.debug("Skipping debounced live stream refresh | user=%s", user_id)
                for session_key, session in list(self._sessions.items()):
                    session_user_id = str(session.get("user_id") or "")
                    if session_user_id != user_id and not str(session_key).startswith(f"{user_id}:"):
                        continue
                    await self._ensure_session_polling(session)
                await on_update(db, user_id)
                return

            for session_key, session in list(self._sessions.items()):
                session_user_id = str(session.get("user_id") or "")
                if session_user_id != user_id and not str(session_key).startswith(f"{user_id}:"):
                    continue
                await self._ensure_session_polling(session)

            primary = self._sessions.get(user_id)
            if primary and primary.get("kind") == "primary":
                last_tick = self._last_price_tick_at.get(user_id)
                started_at = primary.get("started_at")
                now = datetime.now(timezone.utc)
                stale_seconds = None
                if last_tick:
                    stale_seconds = (now - last_tick).total_seconds()
                elif started_at and primary.get("symbols"):
                    stale_seconds = (now - started_at).total_seconds()
                if stale_seconds is not None and stale_seconds > 45:
                    logger.warning(
                        "Restarting stale live market stream | user=%s last_tick_age=%ss",
                        user_id,
                        int(stale_seconds),
                    )
                    await self._stop_primary_stream(user_id)
                    await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=True)
                    await self._ensure_execution_streams(db, user_id, on_update, retry_on_timeout=True)
                    self.mark_stream_refreshed(user_id)
                    return
                if force or uncovered_strategy_symbols:
                    logger.info(
                        "Rebuilding live market stream for strategy symbols | user=%s force=%s uncovered=%s",
                        user_id,
                        force,
                        uncovered_strategy_symbols,
                    )
                    await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=True)
                    await self._ensure_execution_streams(db, user_id, on_update, retry_on_timeout=True)
                    self.mark_stream_refreshed(user_id)
                    return
                self.mark_stream_refreshed(user_id)
                await on_update(db, user_id)
                return

            await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=True)
            await self._ensure_execution_streams(db, user_id, on_update, retry_on_timeout=True)
            self.mark_stream_refreshed(user_id)
            await on_update(db, user_id)

    async def _ensure_session_polling(self, session: dict) -> None:
        connection = session.get("connection")
        symbols = list(session.get("symbols") or [])
        if not connection or not symbols:
            return
        ensure_polling = getattr(connection, "ensure_polling", None)
        if ensure_polling:
            await ensure_polling()
            return
        for symbol in symbols:
            subscribe = getattr(connection, "subscribe_to_market_data", None)
            if subscribe:
                await subscribe(symbol)

    async def _ensure_user_stream(self, db, user_id: str, on_update, retry_on_timeout: bool):
        user_oid = ObjectId(user_id)
        user = await run_sync(db.users.find_one, {"_id": user_oid})
        if not user or not user.get("selected_account_id"):
            await self._stop_primary_stream(user_id)
            return

        account = await run_sync(db.meta_accounts.find_one, {"_id": user["selected_account_id"], "user_id": user_oid})
        if not account:
            await self._stop_primary_stream(user_id)
            return
        if str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
            await self._stop_primary_stream(user_id)
            self._price_cache[user_id] = {}
            await on_update(db, user_id)
            return

        try:
            account_state = await metaapi_service.get_account_connection_state(account["api_token"], account["account_id"])
        except Exception as exc:
            block_reason = f"MetaApi account-state lookup failed ({exc})"
            if self._blocked_reasons.get(user_id) != block_reason:
                logger.warning(
                    "Skipping live market stream | user=%s account=%s reason=%s",
                    user_id,
                    account["account_id"],
                    block_reason,
                )
                self._blocked_reasons[user_id] = block_reason
            await self._stop_primary_stream(user_id)
            self._price_cache[user_id] = {}
            await on_update(db, user_id)
            return

        deployment_state = account_state.get("state")
        connection_status = account_state.get("connection_status")
        block_reason = None

        if deployment_state == "UNDEPLOYED":
            block_reason = f"Undeployed account ignored ({deployment_state})"
        elif deployment_state != "DEPLOYED":
            block_reason = f"Account not deployed yet ({deployment_state or 'UNKNOWN'})"
        elif connection_status != "CONNECTED":
            block_reason = f"Broker connection unavailable ({connection_status or 'UNKNOWN'})"

        if block_reason:
            if self._blocked_reasons.get(user_id) != block_reason:
                log_fn = logger.info if deployment_state == "UNDEPLOYED" else logger.warning
                log_fn(
                    "Skipping live market stream | user=%s account=%s reason=%s",
                    user_id,
                    account["account_id"],
                    block_reason,
                )
                self._blocked_reasons[user_id] = block_reason
            await self._stop_primary_stream(user_id)
            self._price_cache[user_id] = {}
            await on_update(db, user_id)
            return

        self._blocked_reasons.pop(user_id, None)

        symbol_groups = await run_sync(
            _load_primary_stream_symbol_groups,
            db,
            user_oid,
            account["_id"],
        )
        watchlist_symbols = symbol_groups["watchlist_symbols"]
        planner_symbols = symbol_groups["planner_symbols"]
        active_trade_symbols = symbol_groups["active_trade_symbols"]
        trap_symbols = trap_reversal_manager.active_symbols(str(user_oid), account["_id"])
        master_break_symbols = master_break_manager.active_symbols(str(user_oid), account["_id"])
        scheduled_trade_symbols = set(scheduled_trade_manager.active_symbols(str(user_oid), account["_id"]) or set())
        scheduled_trade_symbols |= set(await run_sync(scheduled_trade_manager.active_symbols_from_db, db, user_oid, account["_id"]) or set())
        manual_order_symbols = await run_sync(manual_order_runtime_manager.active_symbols, db, user_oid, account["_id"])
        requested_symbols = sorted(
            watchlist_symbols
            | planner_symbols
            | active_trade_symbols
            | trap_symbols
            | master_break_symbols
            | scheduled_trade_symbols
            | manual_order_symbols
            | self._extra_symbols.get(user_id, set())
        )
        stream_key = f"{str(account['_id'])}:{account['account_id']}"
        existing = self._sessions.get(user_id)

        if not requested_symbols:
            await self._stop_primary_stream(user_id)
            self._price_cache[user_id] = {}
            self._invalid_watchlist_symbols[user_id] = set()
            await on_update(db, user_id)
            return

        try:
            available_symbols = await metaapi_service.get_symbols(account["api_token"], account["account_id"])
        except TimeoutException as exc:
            logger.warning("MetaApi symbol lookup timed out | user=%s account=%s retry=%s error=%s", user_id, account["account_id"], retry_on_timeout, exc)
            await self.stop_user_stream(user_id)
            if retry_on_timeout:
                await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=False)
                return
            raise
        valid_symbols = []
        invalid_symbols = []
        migrated_watchlist_symbols = []
        for symbol in requested_symbols:
            try:
                resolved = resolve_broker_symbol(symbol, list(available_symbols), account)
                if resolved not in valid_symbols:
                    valid_symbols.append(resolved)
                if resolved != symbol and symbol in watchlist_symbols:
                    result = db.watchlist_items.update_one(
                        {"user_id": user_oid, "symbol": symbol},
                        {"$set": {"symbol": resolved}},
                    )
                    if getattr(result, "modified_count", 0):
                        migrated_watchlist_symbols.append((symbol, resolved))
            except HTTPException:
                invalid_symbols.append(symbol)
        valid_symbols = sorted(valid_symbols)
        invalid_symbols = sorted(invalid_symbols)
        if migrated_watchlist_symbols:
            logger.info(
                "Migrated watchlist symbols to broker names | user=%s account=%s migrated=%s",
                user_id,
                account["account_id"],
                migrated_watchlist_symbols,
            )
        invalid_watchlist_symbols = sorted(symbol for symbol in invalid_symbols if symbol in watchlist_symbols)
        self._invalid_watchlist_symbols[user_id] = set(invalid_watchlist_symbols)
        removed_invalid_watchlist = False

        if invalid_symbols:
            logger.warning(
                "Skipping unavailable live symbols | user=%s account=%s invalid=%s",
                user_id,
                account["account_id"],
                invalid_symbols,
            )
            for symbol in invalid_symbols:
                self._price_cache[user_id].pop(symbol, None)
            if invalid_watchlist_symbols:
                result = db.watchlist_items.delete_many({"user_id": user_oid, "symbol": {"$in": invalid_watchlist_symbols}})
                removed_invalid_watchlist = bool(getattr(result, "deleted_count", 0))
                if removed_invalid_watchlist:
                    logger.info(
                        "Removed unavailable symbols from watchlist | user=%s account=%s symbols=%s",
                        user_id,
                        account["account_id"],
                        invalid_watchlist_symbols,
                    )

        if existing and existing["stream_key"] == stream_key and existing["symbols"] == valid_symbols:
            await self._ensure_session_polling(existing)
            if removed_invalid_watchlist:
                await on_update(db, user_id)
            return

        await self._stop_primary_stream(user_id)
        self._price_cache[user_id] = {}

        if not valid_symbols:
            await on_update(db, user_id)
            return

        try:
            connection = await metaapi_service.connect_streaming_account(account["api_token"], account["account_id"])
        except TimeoutException as exc:
            logger.warning("MetaApi stream connect timed out | user=%s account=%s retry=%s error=%s", user_id, account["account_id"], retry_on_timeout, exc)
            await self._stop_primary_stream(user_id)
            if retry_on_timeout:
                await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=False)
                return
            raise
        listener = _MetaPriceListener(self, user_id)
        connection.add_synchronization_listener(listener)

        for symbol in valid_symbols:
            try:
                await connection.subscribe_to_market_data(symbol)
                logger.info("Subscribed live price stream | user=%s symbol=%s", user_id, symbol)
            except TimeoutException as exc:
                logger.warning("MetaApi subscribe timed out | user=%s symbol=%s retry=%s error=%s", user_id, symbol, retry_on_timeout, exc)
                try:
                    await connection.close()
                except Exception:
                    pass
                if retry_on_timeout:
                    await self._stop_primary_stream(user_id)
                    await self._ensure_user_stream(db, user_id, on_update, retry_on_timeout=False)
                    return
                raise
            except Exception:
                logger.exception("Failed to subscribe live price stream | user=%s symbol=%s", user_id, symbol)

        self._sessions[user_id] = {
            "stream_key": stream_key,
            "symbols": valid_symbols,
            "connection": connection,
            "listener": listener,
            "db": db,
            "on_update": on_update,
            "account_db_id": account["_id"],
            "user_id": user_id,
            "cache_prices": True,
            "kind": "primary",
            "account": account,
            "started_at": datetime.now(timezone.utc),
        }
        logger.info("Live market data stream started | user=%s account=%s symbols=%s", user_id, account["account_id"], valid_symbols)
        await on_update(db, user_id)

    async def _ensure_execution_streams(self, db, user_id: str, on_update, retry_on_timeout: bool):
        user_oid = ObjectId(user_id)
        required_accounts = await run_sync(self._required_execution_accounts, db, user_oid)
        active_keys = {
            key for key, session in self._sessions.items()
            if session.get("kind") == "execution" and session.get("user_id") == user_id
        }
        required_keys = {self._execution_session_key(user_id, account_id) for account_id in required_accounts}

        for stale_key in active_keys - required_keys:
            await self._stop_session(stale_key)

        for account_id in required_accounts:
            await self._ensure_execution_stream(db, user_id, account_id, on_update, retry_on_timeout)

    async def _ensure_execution_stream(self, db, user_id: str, account_db_id, on_update, retry_on_timeout: bool):
        user_oid = ObjectId(user_id)
        account = await run_sync(db.meta_accounts.find_one, {"_id": account_db_id, "user_id": user_oid})
        session_key = self._execution_session_key(user_id, account_db_id)
        if not account or str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
            await self._stop_session(session_key)
            return

        requested_symbols = await run_sync(self._required_execution_symbols, db, user_oid, account["_id"])
        existing = self._sessions.get(session_key)
        stream_key = f"{str(account['_id'])}:{account['account_id']}"

        if not requested_symbols:
            await self._stop_session(session_key)
            return

        try:
            account_state = await metaapi_service.get_account_connection_state(account["api_token"], account["account_id"])
        except Exception as exc:
            logger.warning(
                "Skipping planner execution stream | user=%s account=%s reason=account_state_failed error=%s",
                user_id,
                account.get("account_id"),
                exc,
            )
            await self._stop_session(session_key)
            return

        if account_state.get("state") != "DEPLOYED" or account_state.get("connection_status") != "CONNECTED":
            await self._stop_session(session_key)
            return

        try:
            available_symbols = await metaapi_service.get_symbols(account["api_token"], account["account_id"])
            available_symbol_set = {normalize_symbol(symbol) for symbol in available_symbols}
        except TimeoutException as exc:
            logger.warning(
                "MetaApi execution symbol lookup timed out | user=%s account=%s retry=%s error=%s",
                user_id,
                account["account_id"],
                retry_on_timeout,
                exc,
            )
            await self._stop_session(session_key)
            if retry_on_timeout:
                await self._ensure_execution_stream(db, user_id, account_db_id, on_update, retry_on_timeout=False)
            return

        valid_symbols = sorted(
            symbol
            for symbol in requested_symbols
            if normalize_symbol(symbol) in available_symbol_set or symbol in available_symbol_set
        )
        if self._primary_symbols_cover(user_id, account["_id"], set(valid_symbols)):
            if existing:
                await self._stop_session(session_key)
            logger.debug(
                "Skipping duplicate execution stream; primary already covers symbols | user=%s account=%s symbols=%s",
                user_id,
                account["account_id"],
                valid_symbols,
            )
            return
        if existing and existing["stream_key"] == stream_key and existing["symbols"] == valid_symbols:
            await self._ensure_session_polling(existing)
            return

        await self._stop_session(session_key)
        if not valid_symbols:
            return

        try:
            connection = await metaapi_service.connect_streaming_account(account["api_token"], account["account_id"])
        except TimeoutException as exc:
            logger.warning(
                "MetaApi execution stream connect timed out | user=%s account=%s retry=%s error=%s",
                user_id,
                account["account_id"],
                retry_on_timeout,
                exc,
            )
            await self._stop_session(session_key)
            if retry_on_timeout:
                await self._ensure_execution_stream(db, user_id, account_db_id, on_update, retry_on_timeout=False)
            return

        listener = _MetaPriceListener(self, session_key)
        connection.add_synchronization_listener(listener)
        for symbol in valid_symbols:
            try:
                await connection.subscribe_to_market_data(symbol)
                logger.info(
                    "Subscribed planner execution stream | user=%s account=%s symbol=%s",
                    user_id,
                    account["account_id"],
                    symbol,
                )
            except Exception:
                logger.exception(
                    "Failed planner execution stream subscription | user=%s account=%s symbol=%s",
                    user_id,
                    account["account_id"],
                    symbol,
                )

        self._sessions[session_key] = {
            "stream_key": stream_key,
            "symbols": valid_symbols,
            "connection": connection,
            "listener": listener,
            "db": db,
            "on_update": on_update,
            "account_db_id": account["_id"],
            "user_id": user_id,
            "cache_prices": False,
            "kind": "execution",
            "account": account,
        }
        logger.info(
            "Planner execution stream started | user=%s account=%s symbols=%s",
            user_id,
            account["account_id"],
            valid_symbols,
        )

    async def restore_running_streams(self, db, on_update):
        user_ids = await run_sync(_restore_running_user_ids, db)
        for user_id in user_ids:
            await self.ensure_user_stream(db, user_id, on_update)

    async def set_extra_symbols(self, db, user_id: str, symbols: list[str], on_update):
        normalized = {str(symbol).upper() for symbol in symbols if symbol and str(symbol).strip()}
        if normalized == self._extra_symbols.get(user_id, set()):
            return
        self._extra_symbols[user_id] = normalized
        await self.ensure_user_stream(db, user_id, on_update)
        await on_update(db, user_id)

    async def stop_user_stream(self, user_id: str):
        keys = [key for key, session in self._sessions.items() if session.get("user_id") == user_id]
        for key in keys:
            await self._stop_session(key)

    async def _stop_primary_stream(self, user_id: str):
        await self._stop_session(user_id)

    async def _stop_session(self, session_key: str):
        tick_task = self._tick_tasks.pop(session_key, None)
        self._cancel_task_threadsafe(tick_task)
        self._pending_prices.pop(session_key, None)
        self._last_reconcile_at.pop(session_key, None)
        session = self._sessions.pop(session_key, None)
        if not session:
            return
        if session.get("kind") == "primary":
            user_id = str(session.get("user_id") or session_key)
            self._last_price_tick_at.pop(user_id, None)
        try:
            session["connection"].remove_synchronization_listener(session["listener"])
        except Exception:
            pass
        try:
            await session["connection"].close()
        except Exception:
            pass
        logger.info("Live market data stream stopped | session=%s", session_key)

    async def _symbol_spec_for_session(self, session: dict, symbol: str) -> dict:
        specs = session.setdefault("symbol_specs", {})
        cached = specs.get(symbol)
        if cached:
            return cached
        account = session.get("account") or {}
        try:
            spec = await metaapi_service.get_symbol_specification(account["api_token"], account["account_id"], symbol)
        except Exception:
            spec = {"digits": 5, "point": 0.00001, "tickSize": 0.00001}
        specs[symbol] = spec
        return spec

    async def handle_price(self, session_key: str, price: dict):
        await self._run_on_tick_loop(self._handle_price_on_tick_loop, session_key, price)

    async def _handle_price_on_tick_loop(self, session_key: str, price: dict):
        session = self._sessions.get(session_key)
        if not session:
            return
        user_id = session["user_id"]
        raw_symbol = str(price.get("symbol") or "").strip()
        if not raw_symbol:
            return
        cache_key = normalize_symbol(raw_symbol)
        bid = price.get("bid")
        ask = price.get("ask")
        symbol_spec = await self._symbol_spec_for_session(session, raw_symbol)
        if bid is not None:
            bid = normalize_price_to_symbol(bid, symbol_spec)
        if ask is not None:
            ask = normalize_price_to_symbol(ask, symbol_spec)
        price_digits = digits_from_symbol_spec(symbol_spec)
        if session.get("cache_prices"):
            self._price_cache[user_id][cache_key] = {
                "symbol": raw_symbol,
                "bid": bid,
                "ask": ask,
                "price_digits": price_digits,
                "time": self._resolve_tick_timestamp(price).isoformat().replace("+00:00", "Z"),
            }
            self._last_price_tick_at[user_id] = datetime.now(timezone.utc)
        routed_price = {**price, "symbol": raw_symbol}
        self._pending_prices[session_key].append(routed_price)
        task = self._tick_tasks.get(session_key)
        if not task or task.done():
            self._tick_tasks[session_key] = asyncio.create_task(self._process_pending_prices(session_key))

    async def handle_pushed_ticks(self, db, account_id: str | None, ticks: list[dict], on_update) -> int:
        routed = 0
        for raw_tick in ticks:
            price = self._normalize_pushed_tick(raw_tick)
            if not price:
                continue
            routed += await self._route_pushed_tick(db, account_id, price, on_update)
        return routed

    async def _route_pushed_tick(self, db, account_id: str | None, price: dict, on_update) -> int:
        symbol = normalize_symbol(price.get("symbol"))
        account_filter = str(account_id or "").strip()
        matching_sessions = []
        for session_key, session in list(self._sessions.items()):
            session_account = session.get("account") or {}
            session_account_id = str(session_account.get("account_id") or "")
            if account_filter and session_account_id != account_filter and str(session.get("account_db_id") or "") != account_filter:
                continue
            session_symbols = {normalize_symbol(value) for value in (session.get("symbols") or [])}
            if symbol not in session_symbols:
                continue
            matching_sessions.append(session_key)

        for session_key in matching_sessions:
            await self.handle_price(session_key, price)

        if matching_sessions:
            return len(matching_sessions)

        # If no browser/socket session has been established yet, seed any users
        # whose selected international account matches the bridge tick and then
        # retry routing. This keeps strategy runtimes alive after a backend restart.
        for user in await run_sync(_users_for_unseeded_tick, db, account_filter):
            await self.ensure_user_stream(db, user["user_id"], on_update)

        routed = 0
        for session_key, session in list(self._sessions.items()):
            session_account = session.get("account") or {}
            session_account_id = str(session_account.get("account_id") or "")
            if account_filter and session_account_id != account_filter and str(session.get("account_db_id") or "") != account_filter:
                continue
            if symbol in {normalize_symbol(value) for value in (session.get("symbols") or [])}:
                await self.handle_price(session_key, price)
                routed += 1
        return routed

    def _normalize_pushed_tick(self, tick: dict) -> dict | None:
        if not isinstance(tick, dict):
            return None
        symbol = str(tick.get("symbol") or "").strip().upper()
        if not symbol:
            return None
        bid = self._positive_number(tick.get("bid"))
        ask = self._positive_number(tick.get("ask"))
        last = self._positive_number(tick.get("last") or tick.get("price"))
        if bid is None and ask is None and last is None:
            return None
        if bid is None:
            bid = last
        if ask is None:
            ask = last
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "time": tick.get("time") or tick.get("brokerTime") or tick.get("time_iso") or datetime.now(timezone.utc).isoformat(),
        }

    def _positive_number(self, value) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not number or number <= 0:
            return None
        return number

    async def _process_pending_prices(self, session_key: str):
        try:
            while True:
                queue = self._pending_prices.get(session_key)
                if not queue:
                    self._pending_prices.pop(session_key, None)
                    return
                price = queue.popleft()
                session = self._sessions.get(session_key)
                if not session:
                    self._pending_prices.pop(session_key, None)
                    return
                user_id = session["user_id"]
                symbol = price.get("symbol")
                if symbol:
                    logger.debug(
                        "Live tick | session=%s symbol=%s bid=%s ask=%s",
                        session_key,
                        symbol,
                        price.get("bid"),
                        price.get("ask"),
                    )

                await self._process_tick_work(session_key, session, price)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live tick processing failed | session=%s", session_key)

    async def _process_tick_work(self, session_key: str, session: dict, price: dict):
        user_id = session["user_id"]
        tick_lock = self._tick_locks.setdefault(user_id, asyncio.Lock())
        async with tick_lock:
            await self._process_tick_work_locked(session_key, session, price)

    async def _process_tick_work_locked(self, session_key: str, session: dict, price: dict):
        user_id = session["user_id"]
        now = datetime.now(timezone.utc)
        outage_until = self._mongo_outage_until.get(session_key)
        if outage_until and now < outage_until:
            self._schedule_snapshot_update(session)
            return
        tick_time = self._resolve_tick_timestamp(price)
        account_db_id = session.get("account_db_id")
        last_reconcile_at = self._last_reconcile_at.get(session_key)
        reconciled = False
        try:
            if not last_reconcile_at or (now - last_reconcile_at).total_seconds() >= ORDER_RECONCILE_INTERVAL_SECONDS:
                await self._reconcile_live_orders(session["db"], user_id, session)
                self._last_reconcile_at[session_key] = now
                reconciled = True

            account = session.get("account")
            if account_db_id and (not account or account.get("_id") != account_db_id):
                account = await run_sync(session["db"].meta_accounts.find_one, {"_id": account_db_id})
                session["account"] = account
            if reconciled and account:
                await run_coro_in_thread(manual_order_runtime_manager.handle_post_reconcile, session["db"], user_id, account)
                await scheduled_trade_manager.sync_linked_orders(session["db"], ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id, account)
            if account_db_id and account and session.get("kind") == "primary":
                await run_sync(m1_candle_builder.handle_tick, session["db"], user_id, account, price, tick_time)
                await trap_reversal_manager.handle_price(price.get("symbol") or "", price)
                await master_break_manager.handle_price(
                    price.get("symbol") or "",
                    price,
                    db=session.get("db"),
                )
                await scheduled_trade_manager.handle_price(
                    price.get("symbol") or "",
                    price,
                    db=session.get("db"),
                    account=account,
                    user_id=str(user_id),
                )
                await run_coro_in_thread(manual_order_runtime_manager.handle_tick, session["db"], user_id, account, price, tick_time)
            if account:
                await run_coro_in_thread(trade_planner_runtime_manager.handle_tick, session["db"], user_id, account_db_id, account, price)
            self._mongo_outage_until.pop(session_key, None)
            self._schedule_snapshot_update(session)
        except Exception as exc:
            if not _is_mongo_unavailable_error(exc):
                raise
            self._mongo_outage_until[session_key] = now + timedelta(seconds=MONGO_OUTAGE_BACKOFF_SECONDS)
            logger.warning(
                "MongoDB unavailable during live tick work; backing off reconcile/snapshot work | session=%s retry_in=%ss error=%s",
                session_key,
                MONGO_OUTAGE_BACKOFF_SECONDS,
                exc,
            )

    def schedule_background_reconcile(self, db, user_id: str, on_update, include_all_accounts: bool = False) -> None:
        existing = self._background_reconcile_tasks.get(user_id)
        if existing and not existing.done():
            return

        async def _run():
            if user_id in self._background_reconcile_inflight:
                return
            self._background_reconcile_inflight.add(user_id)
            try:
                await self.reconcile_active_orders(db, user_id, include_all_accounts=include_all_accounts)
                await on_update(db, user_id)
            except Exception:
                logger.exception("Background order reconciliation failed | user=%s", user_id)
            finally:
                self._background_reconcile_inflight.discard(user_id)
                task = self._background_reconcile_tasks.get(user_id)
                if task is asyncio.current_task():
                    self._background_reconcile_tasks.pop(user_id, None)

        self._background_reconcile_tasks[user_id] = asyncio.create_task(_run())

    def _resolve_tick_timestamp(self, price: dict) -> datetime:
        raw_time = price.get("time") or price.get("brokerTime") or price.get("time_iso")
        if isinstance(raw_time, datetime):
            normalized = raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
            return normalized.astimezone(timezone.utc).replace(tzinfo=None)
        if raw_time:
            try:
                return datetime.fromisoformat(str(raw_time).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass
        return datetime.utcnow()

    def _schedule_snapshot_update(self, session: dict):
        user_id = session["user_id"]
        existing = self._snapshot_tasks.get(user_id)
        if existing and not existing.done():
            return
        self._snapshot_tasks[user_id] = asyncio.create_task(
            self._run_snapshot_update(session["db"], user_id, session["on_update"])
        )

    async def _run_snapshot_update(self, db, user_id: str, on_update):
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(SNAPSHOT_DEBOUNCE_SECONDS)
            await on_update(db, user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live snapshot update failed | user=%s", user_id)
        finally:
            task = self._snapshot_tasks.get(user_id)
            if task is current_task:
                self._snapshot_tasks.pop(user_id, None)

    def _required_execution_accounts(self, db, user_oid: ObjectId) -> set:
        account_ids = set()
        plan_docs = db[TRADE_PLAN_COLLECTION].find(
            {
                "user_id": user_oid,
                "$or": [
                    {"auto_execution_enabled": True},
                    {
                        "status": "RUNNING",
                    },
                ],
            },
            {"account_targets": 1, "account_id": 1},
        )
        for plan in plan_docs:
            if plan.get("account_targets"):
                for target in plan.get("account_targets") or []:
                    account_id = target.get("account_id")
                    if account_id:
                        account_ids.add(account_id)
            elif plan.get("account_id"):
                account_ids.add(plan["account_id"])

        active_order_accounts = db.orders.distinct(
            "account_id",
            {
                "user_id": user_oid,
                "dry_run": {"$ne": True},
                "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
            },
        )
        for account_id in active_order_accounts:
            if account_id:
                account_ids.add(account_id)
        account_ids.update(trap_reversal_manager.active_account_ids(str(user_oid)))
        account_ids.update(master_break_manager.active_account_ids(str(user_oid)))
        return account_ids

    def _required_execution_symbols(self, db, user_oid: ObjectId, account_db_id) -> set[str]:
        planner_symbols = {
            str(item.get("symbol") or "").upper()
            for item in db[TRADE_PLAN_COLLECTION].find(
                {
                    "user_id": user_oid,
                    "auto_execution_enabled": True,
                    "status": "RUNNING",
                    "$or": [
                        {"account_targets.account_id": account_db_id},
                        {"account_id": account_db_id},
                    ],
                },
                {"symbol": 1},
            )
            if str(item.get("symbol") or "").strip()
        }
        active_trade_symbols = {
            str(item.get("symbol") or "").upper()
            for item in db.orders.find(
                {
                    "user_id": user_oid,
                    "account_id": account_db_id,
                    "dry_run": {"$ne": True},
                    "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
                },
                {"symbol": 1},
            )
            if str(item.get("symbol") or "").strip()
        }
        trap_symbols = trap_reversal_manager.active_symbols(str(user_oid), account_db_id)
        master_break_symbols = master_break_manager.active_symbols(str(user_oid), account_db_id)
        scheduled_trade_symbols = set(scheduled_trade_manager.active_symbols(str(user_oid), account_db_id) or set())
        scheduled_trade_symbols |= set(scheduled_trade_manager.active_symbols_from_db(db, user_oid, account_db_id) or set())
        # Execution streams are for orders/reconcile only; strategy feed comes from primary.
        manual_order_symbols = manual_order_runtime_manager.active_symbols(db, user_oid, account_db_id)
        return planner_symbols | active_trade_symbols | trap_symbols | master_break_symbols | scheduled_trade_symbols | manual_order_symbols

    def _execution_session_key(self, user_id: str, account_db_id) -> str:
        return f"{user_id}:{str(account_db_id)}"

    async def _reconcile_live_orders(self, db, user_id: str, session: dict):
        connection = session.get("connection")
        account_db_id = session.get("account_db_id")
        if not connection or not account_db_id:
            return

        try:
            terminal_state = await connection.get_terminal_state()
            if getattr(terminal_state, "read_ok", True) is False:
                logger.warning("Skipping live order reconciliation after failed terminal-state read | user=%s account=%s", user_id, account_db_id)
                return
            broker_orders = list(getattr(terminal_state, "orders", []) or [])
            broker_positions = list(getattr(terminal_state, "positions", []) or [])
        except Exception:
            logger.exception("Failed to read terminal state for live order reconciliation | user=%s", user_id)
            return

        orders_by_id = {str(item.get("id")): item for item in broker_orders if item.get("id") is not None}
        positions_by_id = {str(item.get("id")): item for item in broker_positions if item.get("id") is not None}
        user_oid = ObjectId(user_id)
        account = db.meta_accounts.find_one({"_id": account_db_id}, {"account_name": 1, "account_id": 1, "meta_profile": 1, "api_token": 1})
        local_orders = list(
            db.orders.find(
                {
                    "user_id": user_oid,
                    "account_id": account_db_id,
                    "dry_run": {"$ne": True},
                    "$or": [
                        {"status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]}},
                        {"status": "CANCELLED", "meta_order_id": {"$nin": [None, ""]}},
                    ],
                }
            ).sort("updated_at", -1)
        )
        logger.info(
            "Reconciling live orders | user=%s account=%s local=%s broker_orders=%s broker_positions=%s",
            user_id,
            account_db_id,
            len(local_orders),
            len(broker_orders),
            len(broker_positions),
        )
        matched_broker_order_ids: set[str] = set()
        matched_broker_position_ids: set[str] = set()

        for order in local_orders:
            current_status = _normalize_order_status(order.get("status"))
            meta_order_id = str(order.get("meta_order_id") or "")
            broker_order = orders_by_id.get(meta_order_id) if meta_order_id else None
            if not broker_order and current_status != "CANCELLED":
                broker_order = _match_broker_order(order, broker_orders)
            if current_status == "CANCELLED" and broker_order and _map_broker_order_state(broker_order.get("state")) == "PENDING":
                if account and meta_order_id:
                    try:
                        await metaapi_service.cancel_order(
                            account["api_token"],
                            account["account_id"],
                            meta_order_id,
                        )
                        broker_order = None
                    except Exception as exc:
                        if is_missing_broker_order_error(exc):
                            broker_order = None
                        else:
                            logger.warning(
                                "Retry cancel failed for locally cancelled pending order | user=%s order=%s error=%s",
                                user_id,
                                order.get("_id"),
                                exc,
                            )
            broker_position = None

            meta_position_id = str(order.get("meta_position_id") or "")
            if meta_position_id:
                broker_position = positions_by_id.get(meta_position_id)

            if not broker_position and broker_order and broker_order.get("positionId"):
                broker_position = positions_by_id.get(str(broker_order.get("positionId")))

            if broker_position and str(broker_position.get("id") or "") in matched_broker_position_ids:
                broker_position = None

            if not broker_position:
                broker_position = _match_broker_position(order, broker_positions, matched_broker_position_ids)

            if broker_order and broker_order.get("id") is not None:
                matched_broker_order_ids.add(str(broker_order.get("id")))
            if broker_position and broker_position.get("id") is not None:
                matched_broker_position_ids.add(str(broker_position.get("id")))

            update_payload = _build_broker_order_update(order, current_status, broker_order, broker_position)
            merged_order = {**order, **(update_payload or {})}
            if account and update_payload:
                if update_payload.get("status") == "CLOSED" and needs_closed_realized_pl_resolution(merged_order):
                    try:
                        resolved = await metaapi_service.resolve_closed_orders_realized_pl(
                            account["api_token"],
                            account["account_id"],
                            [merged_order],
                        )
                        realized = resolved.get(str(order["_id"]))
                        if realized is not None:
                            update_payload["realized_pl"] = realized
                    except Exception:
                        logger.exception(
                            "Failed to resolve closed position P/L during reconciliation | user=%s order=%s",
                            user_id,
                            order.get("_id"),
                        )
                        fallback = merge_realized_pl_on_close(order)
                        if fallback is not None:
                            update_payload["realized_pl"] = fallback
                elif needs_active_booked_pl_resolution(merged_order):
                    try:
                        resolved = await metaapi_service.resolve_active_orders_booked_pl(
                            account["api_token"],
                            account["account_id"],
                            [merged_order],
                        )
                        booked = resolved.get(str(order["_id"]))
                        if booked is not None:
                            update_payload["realized_pl"] = booked
                    except Exception:
                        logger.exception(
                            "Failed to resolve active booked P/L during reconciliation | user=%s order=%s",
                            user_id,
                            order.get("_id"),
                        )
            if update_payload:
                db.orders.update_one({"_id": order["_id"]}, {"$set": update_payload})

        await _import_untracked_broker_orders(
            db,
            user_oid,
            account_db_id,
            account,
            broker_orders,
            broker_positions,
            matched_broker_order_ids,
            matched_broker_position_ids,
        )

    async def enrich_orders_pl(self, db, user_oid: ObjectId, orders: list[dict]) -> list[dict]:
        closed_pending = [order for order in orders if needs_closed_realized_pl_resolution(order)]
        closed_ids = {str(order["_id"]) for order in closed_pending}
        active_pending = [
            order
            for order in orders
            if needs_active_booked_pl_resolution(order) and str(order["_id"]) not in closed_ids
        ]
        pending = closed_pending + active_pending
        if not pending:
            return orders

        by_account: dict[str, list[dict]] = {}
        for order in pending:
            account_id = str(order.get("account_id") or "")
            if account_id:
                by_account.setdefault(account_id, []).append(order)

        updated = {str(order["_id"]): order for order in orders}
        for account_id, account_orders in by_account.items():
            account = db.meta_accounts.find_one({"_id": ObjectId(account_id), "user_id": user_oid})
            if not account or str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
                continue
            closed_orders = [order for order in account_orders if needs_closed_realized_pl_resolution(order)]
            active_orders = [order for order in account_orders if needs_active_booked_pl_resolution(order)]
            try:
                resolved: dict[str, float] = {}
                if closed_orders:
                    resolved.update(
                        await metaapi_service.resolve_closed_orders_realized_pl(
                            account["api_token"],
                            account["account_id"],
                            closed_orders,
                        )
                    )
                if active_orders:
                    resolved.update(
                        await metaapi_service.resolve_active_orders_booked_pl(
                            account["api_token"],
                            account["account_id"],
                            active_orders,
                        )
                    )
            except Exception:
                logger.exception(
                    "Failed to resolve order P/L | user=%s account=%s orders=%s",
                    user_oid,
                    account.get("account_id"),
                    len(account_orders),
                )
                continue
            for order in account_orders:
                order_key = str(order["_id"])
                realized = resolved.get(order_key)
                if realized is None:
                    continue
                db.orders.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"realized_pl": realized, "updated_at": datetime.utcnow()}},
                )
                updated[order_key] = {**order, "realized_pl": realized}

        return [updated[str(order["_id"])] for order in orders]

    async def resolve_closed_orders_pl(self, db, user_oid: ObjectId, orders: list[dict]) -> list[dict]:
        return await self.enrich_orders_pl(db, user_oid, orders)

    async def _backfill_closed_order_realized_pl(self, db, user_oid: ObjectId) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        missing = list(
            db.orders.find(
                {
                    "user_id": user_oid,
                    "dry_run": {"$ne": True},
                    "status": "CLOSED",
                    "$and": [
                        {"$or": [{"realized_pl": None}, {"realized_pl": 0}]},
                        {
                            "$or": [
                                {"closed_at": {"$gte": cutoff}},
                                {"updated_at": {"$gte": cutoff}},
                            ]
                        },
                    ],
                },
                {"account_id": 1, "meta_position_id": 1, "meta_order_id": 1, "symbol": 1, "realized_pl": 1, "unrealized_pl": 1, "last_broker_profit": 1, "opened_at": 1, "closed_at": 1},
            ).limit(50)
        )
        if missing:
            await self.resolve_closed_orders_pl(db, user_oid, missing)

    async def reconcile_active_orders(self, db, user_id: str, force: bool = False, include_all_accounts: bool = False):
        user_oid = ObjectId(user_id)
        now = datetime.now(timezone.utc)
        last_reconcile_at = self._last_direct_reconcile_at.get(user_id)
        if not force and last_reconcile_at and (now - last_reconcile_at).total_seconds() < BACKGROUND_RECONCILE_INTERVAL_SECONDS:
            await self._backfill_closed_order_realized_pl(db, user_oid)
            return
        self._last_direct_reconcile_at[user_id] = now
        active_account_ids = set(db.orders.distinct(
            "account_id",
            {
                "user_id": user_oid,
                "dry_run": {"$ne": True},
                "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
            },
        ))
        if include_all_accounts:
            account_docs = list(db.meta_accounts.find({"user_id": user_oid}))
            active_account_ids.update(
                account["_id"]
                for account in account_docs
                if str(account.get("market_type") or "INTERNATIONAL").upper() == "INTERNATIONAL"
            )
        for account_db_id in active_account_ids:
            if not account_db_id:
                continue
            account = db.meta_accounts.find_one({"_id": account_db_id, "user_id": user_oid})
            if not account or str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
                continue
            connection = None
            try:
                connection = await metaapi_service.connect_streaming_account(account["api_token"], account["account_id"])
                await self._reconcile_live_orders(
                    db,
                    user_id,
                    {
                        "connection": connection,
                        "account_db_id": account["_id"],
                    },
                )
            except Exception:
                logger.exception("Direct broker order reconciliation failed | user=%s account=%s", user_id, account.get("account_id"))
            finally:
                if connection:
                    try:
                        await connection.close()
                    except Exception:
                        pass
        await self._backfill_closed_order_realized_pl(db, user_oid)


market_data_stream = MarketDataStreamManager()


def _normalize_order_status(value) -> str:
    return str(value or "UNKNOWN").upper()


def _build_broker_order_update(order: dict, current_status: str, broker_order: Optional[dict], broker_position: Optional[dict]) -> Optional[dict]:
    now = datetime.utcnow()
    payload = {"updated_at": now}
    changed = False

    if current_status == "CANCELLED" and not broker_order:
        if order.get("broker_cancel_pending"):
            payload["broker_cancel_pending"] = False
            payload["last_broker_seen_at"] = now
            return payload
        return None

    if broker_position:
        volume = broker_position.get("volume")
        next_status = "POSITION_OPEN"
        try:
            if volume is not None and float(volume) < float(order.get("quantity") or volume):
                next_status = "PARTIALLY_CLOSED"
        except (TypeError, ValueError):
            pass
        unrealized = broker_position.get("unrealizedProfit")
        total_profit = broker_position.get("profit")
        realized = order.get("realized_pl")
        try:
            if total_profit is not None and unrealized is not None and abs(float(total_profit) - float(unrealized)) > 1e-9:
                realized = round(float(total_profit) - float(unrealized), 2)
        except (TypeError, ValueError):
            realized = order.get("realized_pl")

        open_price = broker_position.get("openPrice")
        broker_stop_loss = broker_position.get("stopLoss")
        next_values = {
            "status": next_status,
            "is_open_position": True,
            "position_quantity": float(volume) if volume is not None else order.get("position_quantity"),
            "unrealized_pl": float(unrealized) if unrealized is not None else (
                float(total_profit) if total_profit is not None else order.get("unrealized_pl")
            ),
            "realized_pl": round(float(realized), 2) if realized is not None else order.get("realized_pl"),
            "meta_position_id": str(broker_position.get("id")) if broker_position.get("id") is not None else order.get("meta_position_id"),
            "broker_missing_since": None,
            "last_broker_seen_at": now,
            "opened_at": order.get("opened_at") or now,
        }
        try:
            if total_profit is not None:
                next_values["last_broker_profit"] = round(float(total_profit), 2)
            elif unrealized is not None:
                next_values["last_broker_profit"] = round(float(unrealized), 2)
        except (TypeError, ValueError):
            pass
        if open_price is not None:
            try:
                fill_entry = float(open_price)
                if fill_entry > 0 and not order.get("entry"):
                    next_values["entry"] = fill_entry
            except (TypeError, ValueError):
                pass
        if broker_stop_loss is not None:
            try:
                broker_sl = float(broker_stop_loss)
                if broker_sl > 0 and not order.get("stop_loss"):
                    next_values["stop_loss"] = broker_sl
            except (TypeError, ValueError):
                pass
        for key, value in next_values.items():
            if order.get(key) != value:
                payload[key] = value
                changed = True
        return payload if changed else None

    if broker_order:
        next_status = _map_broker_order_state(broker_order.get("state"))
        if current_status == "CANCELLED" and next_status == "PENDING":
            if order.get("last_broker_seen_at") != now:
                return {"last_broker_seen_at": now, "broker_cancel_pending": True}
            return None
        next_values = {
            "status": next_status,
            "is_open_position": False,
            "meta_position_id": str(broker_order.get("positionId")) if broker_order.get("positionId") is not None else order.get("meta_position_id"),
            "broker_missing_since": None,
            "last_broker_seen_at": now,
        }
        volume = broker_order.get("volume")
        if volume is not None:
            next_values["position_quantity"] = float(volume)
        if next_status == "PENDING":
            next_values["opened_at"] = order.get("opened_at") or order.get("created_at") or now
        if next_status == "CANCELLED":
            next_values["position_quantity"] = 0.0
            next_values["unrealized_pl"] = None
            next_values["closed_at"] = order.get("closed_at") or now
        for key, value in next_values.items():
            if order.get(key) != value:
                payload[key] = value
                changed = True
        return payload if changed else None

    if current_status in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}:
        missing_since = order.get("broker_missing_since")
        next_missing = now if not isinstance(missing_since, datetime) else missing_since
        if isinstance(next_missing, datetime) and (now - next_missing) >= timedelta(seconds=BROKER_MISSING_CONFIRMATION_SECONDS):
            next_values = {
                "status": "CLOSED",
                "is_open_position": False,
                "position_quantity": 0.0,
                "unrealized_pl": None,
                "realized_pl": merge_realized_pl_on_close(order),
                "broker_missing_since": None,
                "closed_at": order.get("closed_at") or now,
            }
            for key, value in next_values.items():
                if order.get(key) != value:
                    payload[key] = value
                    changed = True
            return payload if changed else None
        if order.get("broker_missing_since") != next_missing:
            payload["broker_missing_since"] = next_missing
            changed = True
        return payload if changed else None

    if current_status in {"PENDING", "PLACEMENT_PENDING"}:
        if order.get("meta_order_id"):
            next_values = {
                "status": "CANCELLED",
                "is_open_position": False,
                "position_quantity": 0.0,
                "unrealized_pl": None,
                "broker_missing_since": None,
                "closed_at": order.get("closed_at") or now,
                "last_broker_seen_at": now,
            }
            for key, value in next_values.items():
                if order.get(key) != value:
                    payload[key] = value
                    changed = True
            return payload if changed else None

        missing_since = order.get("broker_missing_since")
        next_missing = now if not isinstance(missing_since, datetime) else missing_since
        if order.get("broker_missing_since") != next_missing:
            payload["broker_missing_since"] = next_missing
            changed = True
        return payload if changed else None
    return None


def _map_broker_order_state(state) -> str:
    upper = str(state or "").upper()
    if upper in {"2", "6", "ORDER_STATE_CANCELED", "ORDER_STATE_CANCELLED", "ORDER_STATE_EXPIRED"}:
        return "CANCELLED"
    if upper in {"5", "ORDER_STATE_REJECTED"}:
        return "FAILED"
    return "PENDING"


def _match_broker_order(order: dict, broker_orders: list[dict]) -> Optional[dict]:
    symbol = str(order.get("symbol") or "").upper()
    if not symbol:
        return None
    expected_order_type = str(order.get("order_type") or "").upper()
    expected_side = str(order.get("side") or "").upper()
    try:
        expected_entry = float(order.get("entry"))
    except (TypeError, ValueError):
        expected_entry = None
    try:
        expected_quantity = float(order.get("quantity"))
    except (TypeError, ValueError):
        expected_quantity = None

    candidates = []
    for broker_order in broker_orders:
        if str(broker_order.get("symbol") or "").upper() != symbol:
            continue
        order_type, side = _infer_order_type_and_side(broker_order)
        if expected_order_type and order_type != expected_order_type:
            continue
        if expected_side and side != expected_side:
            continue
        if expected_quantity is not None:
            try:
                if abs(float(broker_order.get("volume") or 0) - expected_quantity) > 1e-8:
                    continue
            except (TypeError, ValueError):
                continue
        candidates.append(broker_order)

    if not candidates:
        return None
    if expected_entry is None:
        return candidates[0]
    return min(candidates, key=lambda item: abs(float(item.get("openPrice") or 0.0) - expected_entry))


def _match_broker_position(order: dict, broker_positions: list[dict], excluded_position_ids: Optional[set[str]] = None) -> Optional[dict]:
    excluded_position_ids = excluded_position_ids or set()
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    expected_side = side if side in {"BUY", "SELL"} else ""
    candidates = [
        position for position in broker_positions
        if str(position.get("symbol") or "").upper() == symbol
        and (not expected_side or _infer_position_side(position) == expected_side)
        and str(position.get("id") or "") not in excluded_position_ids
    ]
    if not candidates:
        try:
            expected_quantity = float(order.get("quantity"))
        except (TypeError, ValueError):
            expected_quantity = None
        if expected_quantity is not None:
            candidates = [
                position for position in broker_positions
                if str(position.get("symbol") or "").upper() == symbol
                and abs(float(position.get("volume") or 0) - expected_quantity) <= 1e-8
                and str(position.get("id") or "") not in excluded_position_ids
            ]
    if not candidates:
        return None
    try:
        entry = float(order.get("entry"))
        return min(candidates, key=lambda position: abs(float(position.get("openPrice") or 0.0) - entry))
    except (TypeError, ValueError):
        return candidates[0]


def _broker_info_from_account(account: Optional[dict]) -> dict:
    if not account:
        return {}
    meta_profile = account.get("meta_profile") or {}
    account_name = str(account.get("account_name") or meta_profile.get("account_name") or "")
    account_id = str(account.get("account_id") or "")
    login = str(meta_profile.get("login") or "")
    server = str(meta_profile.get("server") or "")
    payload = {
        "account_name": account_name,
        "account_id": account_id,
        "login": login,
        "server": server,
    }
    return {key: value for key, value in payload.items() if value}


def _infer_order_type_and_side(broker_order: dict) -> tuple[str, str]:
    raw_type = str(broker_order.get("type") or "").upper()
    numeric_type_map = {
        "0": ("MARKET", "BUY"),
        "1": ("MARKET", "SELL"),
        "2": ("LIMIT", "BUY"),
        "3": ("LIMIT", "SELL"),
        "4": ("SL", "BUY"),
        "5": ("SL", "SELL"),
        "6": ("SL", "BUY"),
        "7": ("SL", "SELL"),
    }
    if raw_type in numeric_type_map:
        return numeric_type_map[raw_type]
    if "SELL" in raw_type:
        side = "SELL"
    else:
        side = "BUY"
    if "LIMIT" in raw_type:
        order_type = "LIMIT"
    elif "STOP" in raw_type:
        order_type = "SL"
    else:
        order_type = "MARKET"
    return order_type, side


def _infer_position_side(broker_position: dict) -> str:
    raw_type = str(broker_position.get("type") or "").upper()
    if raw_type == "1":
        return "SELL"
    if raw_type == "0":
        return "BUY"
    return "SELL" if "SELL" in raw_type else "BUY"


async def _import_untracked_broker_orders(
    db,
    user_oid: ObjectId,
    account_db_id,
    account: Optional[dict],
    broker_orders: list[dict],
    broker_positions: list[dict],
    matched_broker_order_ids: set[str],
    matched_broker_position_ids: set[str],
):
    broker_info = _broker_info_from_account(account)
    now = datetime.utcnow()

    for broker_order in broker_orders:
        broker_order_id = broker_order.get("id")
        if broker_order_id is None or str(broker_order_id) in matched_broker_order_ids:
            continue
        if db.orders.find_one({"user_id": user_oid, "account_id": account_db_id, "meta_order_id": str(broker_order_id)}):
            continue
        order_type, side = _infer_order_type_and_side(broker_order)
        volume = broker_order.get("volume")
        open_price = broker_order.get("openPrice")
        stop_loss = broker_order.get("stopLoss")
        take_profit = broker_order.get("takeProfit")
        state = _map_broker_order_state(broker_order.get("state"))
        db.orders.insert_one(
            {
                "user_id": user_oid,
                "account_id": account_db_id,
                "symbol": str(broker_order.get("symbol") or "").upper(),
                "order_type": order_type,
                "side": side,
                "entry": float(open_price) if open_price is not None else None,
                "stop_loss": float(stop_loss) if stop_loss is not None else None,
                "target": float(take_profit) if take_profit is not None else None,
                "comment": "Imported from broker",
                "quantity": float(volume) if volume is not None else None,
                "risk_amount": None,
                "sl_pips": None,
                "rr_ratio": None,
                "meta_order_id": str(broker_order_id),
                "meta_position_id": str(broker_order.get("positionId")) if broker_order.get("positionId") is not None else None,
                "status": state,
                "failure_reason": None,
                "copy_group_id": None,
                "created_at": now,
                "updated_at": now,
                "opened_at": now,
                "closed_at": now if state == "CANCELLED" else None,
                "last_broker_seen_at": now,
                "is_open_position": False,
                "position_quantity": float(volume) if volume is not None else None,
                "realized_pl": None,
                "unrealized_pl": None,
                "broker_info": broker_info,
                "external_source": "BROKER_IMPORT",
            }
        )

    for broker_position in broker_positions:
        broker_position_id = broker_position.get("id")
        if broker_position_id is None or str(broker_position_id) in matched_broker_position_ids:
            continue
        if db.orders.find_one({"user_id": user_oid, "account_id": account_db_id, "meta_position_id": str(broker_position_id)}):
            continue
        side = _infer_position_side(broker_position)
        volume = broker_position.get("volume")
        open_price = broker_position.get("openPrice")
        stop_loss = broker_position.get("stopLoss")
        take_profit = broker_position.get("takeProfit")
        unrealized = broker_position.get("unrealizedProfit")
        total_profit = broker_position.get("profit")
        realized = None
        try:
            if total_profit is not None and unrealized is not None:
                realized = round(float(total_profit) - float(unrealized), 2)
        except (TypeError, ValueError):
            realized = None
        db.orders.insert_one(
            {
                "user_id": user_oid,
                "account_id": account_db_id,
                "symbol": str(broker_position.get("symbol") or "").upper(),
                "order_type": "MARKET",
                "side": side,
                "entry": float(open_price) if open_price is not None else None,
                "stop_loss": float(stop_loss) if stop_loss is not None else None,
                "target": float(take_profit) if take_profit is not None else None,
                "comment": "Imported from broker",
                "quantity": float(volume) if volume is not None else None,
                "risk_amount": None,
                "sl_pips": None,
                "rr_ratio": None,
                "meta_order_id": None,
                "meta_position_id": str(broker_position_id),
                "status": "POSITION_OPEN",
                "failure_reason": None,
                "copy_group_id": None,
                "created_at": now,
                "updated_at": now,
                "opened_at": now,
                "closed_at": None,
                "last_broker_seen_at": now,
                "is_open_position": True,
                "position_quantity": float(volume) if volume is not None else None,
                "realized_pl": realized,
                "unrealized_pl": float(unrealized) if unrealized is not None else (float(total_profit) if total_profit is not None else None),
                "broker_info": broker_info,
                "external_source": "BROKER_IMPORT",
            }
        )
