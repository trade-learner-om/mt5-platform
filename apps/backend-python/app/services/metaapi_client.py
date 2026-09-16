from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from ..config import settings
from .risk import normalize_price_to_symbol, normalize_volume_to_risk, pip_size_for_symbol, symbol_uses_pips
from .order_logging import append_order_log_prices
from .mt5_order_types import infer_order_type_and_side
from .mt5_symbol_utils import match_available_symbol_name, mt5_symbol_candidates
from .symbol_resolver import normalize_symbol
from .secret_store import decrypt_secret

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - local Windows dependency
    mt5 = None

try:
    from app.mt5.terminal_detection import find_running_terminal_paths
except Exception:  # pragma: no cover - fallback for copied reference layout
    def find_running_terminal_paths() -> list[str]:
        return []


logger = logging.getLogger(__name__)

class LocalMT5Error(RuntimeError):
    pass


ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2


def is_hedging_margin_mode(margin_mode: Any) -> bool:
    try:
        return int(margin_mode) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
    except (TypeError, ValueError):
        return False


def is_missing_broker_order_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    markers = (
        "not found",
        "does not exist",
        "no order",
        "order not found",
        "position not found",
        "pending order not found",
        "already_cancelled",
    )
    return any(marker in message for marker in markers)


def _coming_friday_expiry_utc(reference: Optional[datetime] = None) -> datetime:
    """Upcoming Friday 23:59:59 in IST, returned as a timezone-aware UTC datetime.

    Fresh-position pending orders use this so unfilled Stop/Limit orders auto-cancel
    at the broker by the end of the trading week. If the reference moment is already
    at/after this week's Friday 23:59:59 IST, it rolls to the next Friday.
    """
    ist = ZoneInfo("Asia/Kolkata")
    now_ist = (reference or datetime.now(timezone.utc)).astimezone(ist)
    days_ahead = (4 - now_ist.weekday()) % 7  # Monday=0 ... Friday=4
    candidate = (now_ist + timedelta(days=days_ahead)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    if candidate <= now_ist:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


_SYMBOL_EXPIRATION_SPECIFIED_BIT = 4  # SYMBOL_EXPIRATION_SPECIFIED bitmask flag


def _symbol_supports_specified_expiration(info) -> bool:
    """True when the symbol allows pending orders with an explicit expiration time."""
    specified_flag = getattr(mt5, "SYMBOL_EXPIRATION_SPECIFIED", _SYMBOL_EXPIRATION_SPECIFIED_BIT)
    try:
        expiration_mode = int(getattr(info, "expiration_mode", 0) or 0)
    except (TypeError, ValueError):
        return False
    return bool(expiration_mode & specified_flag)


# SYMBOL_FILLING_* bit flags (MetaTrader5 constants; fall back when package missing).
_SYMBOL_FILLING_FOK = 1
_SYMBOL_FILLING_IOC = 2
_SYMBOL_FILLING_RETURN = 4


def _order_filling_mode(info) -> int:
    """Pick an ORDER_FILLING_* mode allowed by the symbol's filling_mode bitmask.

    Many brokers reject TRADE_ACTION_DEAL with ORDER_FILLING_RETURN (retcode 10030).
    Prefer FOK, then IOC, then RETURN — the usual MT5 order of preference.
    """
    fok = getattr(mt5, "ORDER_FILLING_FOK", 0) if mt5 is not None else 0
    ioc = getattr(mt5, "ORDER_FILLING_IOC", 1) if mt5 is not None else 1
    ret = getattr(mt5, "ORDER_FILLING_RETURN", 2) if mt5 is not None else 2
    symbol_fok = getattr(mt5, "SYMBOL_FILLING_FOK", _SYMBOL_FILLING_FOK) if mt5 is not None else _SYMBOL_FILLING_FOK
    symbol_ioc = getattr(mt5, "SYMBOL_FILLING_IOC", _SYMBOL_FILLING_IOC) if mt5 is not None else _SYMBOL_FILLING_IOC
    symbol_ret = getattr(mt5, "SYMBOL_FILLING_RETURN", _SYMBOL_FILLING_RETURN) if mt5 is not None else _SYMBOL_FILLING_RETURN
    try:
        filling_mode = int(getattr(info, "filling_mode", 0) or 0)
    except (TypeError, ValueError):
        filling_mode = 0
    if filling_mode & symbol_fok:
        return fok
    if filling_mode & symbol_ioc:
        return ioc
    if filling_mode & symbol_ret:
        return ret
    # Unknown / empty bitmask: try IOC then FOK then RETURN (common for market deals).
    return ioc if ioc is not None else (fok if fok is not None else ret)


def _filling_mode_diag(info, chosen: int) -> str:
    try:
        filling_mode = int(getattr(info, "filling_mode", 0) or 0)
    except (TypeError, ValueError):
        filling_mode = 0
    return f"type_filling={chosen} symbol_filling_mode={filling_mode}"


def _mt5_friday_expiration_timestamp(tick) -> int:
    """Encode the upcoming Friday 23:59:59 IST as an MT5 expiration timestamp.

    MT5 interprets a pending order's expiration in the broker server's time zone, so
    the target UTC instant is shifted by the broker's offset (inferred from the last
    tick time, which the terminal reports in server time) before encoding.
    """
    target_utc = _coming_friday_expiry_utc()
    utc_now_epoch = int(datetime.now(timezone.utc).timestamp())
    server_offset_seconds = 0
    tick_time = int(getattr(tick, "time", 0) or 0)
    if tick_time:
        server_offset_seconds = tick_time - utc_now_epoch
    return int(target_utc.timestamp()) + server_offset_seconds


def _symbol_spec_from_info(info) -> dict:
    data = info._asdict()
    return {
        "point": float(data.get("point") or 0),
        "tickSize": float(data.get("trade_tick_size") or data.get("point") or 0),
        "digits": int(data.get("digits") or 0),
        "volumeStep": float(data.get("volume_step") or 0.01),
        "volumeMin": float(data.get("volume_min") or 0.01),
        "volumeMax": float(data.get("volume_max") or 100),
    }


def _normalize_order_price(value: Optional[float], symbol_spec: dict) -> float:
    if value is None or float(value or 0) <= 0:
        return 0.0
    return normalize_price_to_symbol(float(value), symbol_spec)


def _last_error_message(default: str) -> str:
    if mt5 is None:
        return default
    error = mt5.last_error()
    if not error:
        return default
    code, message = error
    return f"{default} MT5 error {code}: {message}"


def _find_mt5_symbol_name(requested: str) -> str:
    requested = str(requested or "").strip()
    if not requested:
        raise LocalMT5Error("Symbol is required.")
    if mt5 is None:
        raise LocalMT5Error(f"Unable to select symbol {requested}.")

    last_error = None
    for candidate in mt5_symbol_candidates(requested):
        if mt5.symbol_select(candidate, True):
            info = mt5.symbol_info(candidate)
            if info is not None:
                return str(getattr(info, "name", None) or candidate)
        last_error = _last_error_message(f"Unable to select symbol {candidate}.")

    available_names = [str(getattr(item, "name", "") or "").strip() for item in (mt5.symbols_get() or [])]
    matched = match_available_symbol_name(requested, available_names)
    if matched and mt5.symbol_select(matched, True):
        info = mt5.symbol_info(matched)
        if info is not None:
            return str(getattr(info, "name", None) or matched)
        last_error = _last_error_message(f"Unable to select symbol {matched}.")

    raise LocalMT5Error(last_error or _last_error_message(f"Unable to select symbol {requested}."))


class LocalMT5Connection:
    def __init__(self, service: "MetaApiService", token: str, account_id: str):
        self.service = service
        self.token = token
        self.account_id = account_id
        self._listeners: list[Any] = []
        self._subscriptions: set[str] = set()
        self._poll_task: asyncio.Task | None = None
        self._poll_failure_counts: dict[str, int] = {}

    def add_synchronization_listener(self, listener: Any) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_synchronization_listener(self, listener: Any) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def close(self) -> None:
        await self.service.release_streaming_connection(self.token, self.account_id)

    async def _shutdown_polling(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        self._subscriptions.clear()
        self._listeners.clear()

    async def connect(self) -> None:
        await self.service._with_session(self.token, self.account_id, lambda: True)

    async def wait_synchronized(self) -> None:
        return None

    async def get_account_information(self) -> dict:
        return await self.service.get_account_information(self.token, self.account_id)

    async def get_symbol_price(self, symbol: str) -> dict:
        return await self.service.get_symbol_price(self.token, self.account_id, symbol)

    async def get_candle(self, symbol: str, timeframe: str) -> dict:
        return await self.service.get_candle(self.token, self.account_id, symbol, timeframe)

    async def get_symbols(self) -> list[str]:
        return await self.service.get_symbols(self.token, self.account_id)

    async def get_symbol_specification(self, symbol: str) -> dict:
        return await self.service.get_symbol_specification(self.token, self.account_id, symbol)

    async def subscribe_to_market_data(self, symbol: str) -> None:
        cleaned = str(symbol or "").strip()
        if not cleaned:
            return
        normalized = normalize_symbol(cleaned)
        self._subscriptions = {existing for existing in self._subscriptions if normalize_symbol(existing) != normalized}
        self._subscriptions.add(cleaned)
        await self.ensure_polling()

    async def ensure_polling(self) -> None:
        if not self._subscriptions:
            return
        if self._poll_task and not self._poll_task.done():
            return
        restarting = self._poll_task is not None
        message = "Restarting local MT5 price polling" if restarting else "Starting local MT5 price polling"
        log = logger.warning if restarting else logger.info
        log(
            "%s | account=%s symbols=%s",
            message,
            self.account_id,
            sorted(self._subscriptions),
        )
        self._poll_task = asyncio.create_task(self._poll_prices())

    async def _poll_prices(self) -> None:
        while True:
            for symbol in list(self._subscriptions):
                try:
                    price = await asyncio.wait_for(self.get_symbol_price(symbol), timeout=10.0)
                    self._poll_failure_counts.pop(symbol, None)
                except asyncio.TimeoutError:
                    failures = self._poll_failure_counts.get(symbol, 0) + 1
                    self._poll_failure_counts[symbol] = failures
                    if failures == 1 or failures % 60 == 0:
                        logger.warning("Local MT5 price polling timed out | symbol=%s failures=%s", symbol, failures)
                    continue
                except LocalMT5Error as exc:
                    failures = self._poll_failure_counts.get(symbol, 0) + 1
                    self._poll_failure_counts[symbol] = failures
                    if failures == 1 or failures % 60 == 0:
                        logger.warning("Local MT5 price polling skipped | symbol=%s failures=%s error=%s", symbol, failures, exc)
                    continue
                except Exception:
                    logger.exception("Local MT5 price polling failed | symbol=%s", symbol)
                    continue
                for listener in list(self._listeners):
                    callback = getattr(listener, "on_symbol_price_updated", None)
                    if callback:
                        await callback(None, price)
            await asyncio.sleep(1.0)

    async def get_terminal_state(self):
        return await self.service.get_terminal_state(self.token, self.account_id)


class LocalMT5StreamingPool:
    def __init__(self, service: "MetaApiService"):
        self._service = service
        self._connections: dict[str, LocalMT5Connection] = {}
        self._ref_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _key(self, token: str, account_id: str) -> str:
        return self._service._session_manager._session_key(token, account_id)

    async def acquire(self, token: str, account_id: str) -> LocalMT5Connection:
        async with self._lock:
            key = self._key(token, account_id)
            connection = self._connections.get(key)
            if connection is None:
                connection = LocalMT5Connection(self._service, token, account_id)
                await connection.connect()
                self._connections[key] = connection
            self._ref_counts[key] = self._ref_counts.get(key, 0) + 1
            return connection

    async def release(self, token: str, account_id: str) -> None:
        connection = None
        async with self._lock:
            key = self._key(token, account_id)
            current = self._ref_counts.get(key, 0)
            if current <= 0:
                return
            current -= 1
            if current > 0:
                self._ref_counts[key] = current
                return
            self._ref_counts.pop(key, None)
            connection = self._connections.pop(key, None)
        if connection is not None:
            await connection._shutdown_polling()


class LocalMT5SessionManager:
    def __init__(self, service: "MetaApiService"):
        self._service = service
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    async def run(self, token: str, account_id: str, operation):
        return await asyncio.to_thread(self._run_sync, token, account_id, operation)

    def _run_sync(self, token: str, account_id: str, operation):
        session_key = self._session_key(token, account_id)
        lock = self._lock_for(session_key)
        with lock:
            return self._service._run_session_sync(token, account_id, operation)

    def _lock_for(self, session_key: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._locks.get(session_key)
            if lock is None:
                lock = threading.RLock()
                self._locks[session_key] = lock
            return lock

    def _session_key(self, token: str, account_id: str) -> str:
        credentials = self._service._decode_credentials(token)
        path = str(credentials.get("path") or "").strip()
        server = str(credentials.get("server") or "").strip().upper()
        return f"{account_id}:{server}:{path}"


class MetaApiService:
    """
    Compatibility service for the reference app's MetaApi contract.

    International broker operations are backed by the local MetaTrader5 terminal.
    The method names are intentionally kept as-is so the copied workflow can keep
    using the reference app route and service contracts.
    """

    def __init__(self):
        self._symbols_cache: dict[str, list[str]] = {}
        self._session_manager = LocalMT5SessionManager(self)
        self._streaming_pool = LocalMT5StreamingPool(self)

    async def connect_account(self, token: str, account_id: str):
        connection = LocalMT5Connection(self, token, account_id)
        await connection.connect()
        return connection

    async def connect_streaming_account(self, token: str, account_id: str):
        return await self._streaming_pool.acquire(token, account_id)

    async def release_streaming_connection(self, token: str, account_id: str) -> None:
        await self._streaming_pool.release(token, account_id)

    async def get_account_connection_state(self, token: str, account_id: str) -> dict:
        await self._with_session(token, account_id, lambda: True)
        return {"state": "DEPLOYED", "connection_status": "CONNECTED", "region": "local"}

    async def get_account_information(self, token: str, account_id: str) -> dict:
        def operation():
            info = mt5.account_info()
            if info is None:
                raise LocalMT5Error(_last_error_message("MT5 account information unavailable."))
            data = info._asdict()
            margin_mode = data.get("margin_mode")
            return {
                "name": data.get("name"),
                "login": data.get("login"),
                "server": data.get("server"),
                "company": data.get("company"),
                "balance": data.get("balance"),
                "equity": data.get("equity"),
                "currency": data.get("currency"),
                "margin": data.get("margin"),
                "margin_free": data.get("margin_free"),
                "leverage": data.get("leverage"),
                "margin_mode": margin_mode,
                "is_hedging_account": is_hedging_margin_mode(margin_mode),
            }

        return await self._with_session(token, account_id, operation)

    async def get_account_profile(self, token: str, account_id: str) -> dict:
        account_info = await self.get_account_information(token, account_id)
        login = str(account_info.get("login") or account_id)
        server = str(account_info.get("server") or self._decode_credentials(token).get("server") or "")
        display_name = str(account_info.get("name") or account_info.get("company") or login)
        return {
            "account_name": display_name,
            "metaapi_account_id": login,
            "login": login,
            "type": "MT5_LOCAL",
            "server": server,
            "company": str(account_info.get("company") or ""),
        }

    async def get_account_profile_with_equity(self, token: str, account_id: str) -> dict:
        profile = await self.get_account_profile(token, account_id)
        account_info = await self.get_account_information(token, account_id)
        return {
            **profile,
            "equity": float(account_info.get("equity") or 0),
            "balance": float(account_info.get("balance") or 0),
            "currency": str(account_info.get("currency") or "USD"),
        }

    async def get_symbol_price(self, token: str, account_id: str, symbol: str) -> dict:
        requested = str(symbol or "").strip()

        def operation():
            resolved_symbol = _find_mt5_symbol_name(requested)
            tick = mt5.symbol_info_tick(resolved_symbol)
            if tick is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 tick available for {resolved_symbol}."))
            data = tick._asdict()
            return {
                "symbol": resolved_symbol,
                "bid": float(data.get("bid") or 0),
                "ask": float(data.get("ask") or 0),
                "time": datetime.fromtimestamp(data.get("time") or 0, tz=timezone.utc).isoformat(),
            }

        return await self._with_session(token, account_id, operation)

    async def get_candle(self, token: str, account_id: str, symbol: str, timeframe: str) -> dict:
        candles = await self.get_historical_candles(token, account_id, symbol, timeframe, limit=1)
        return candles[-1] if candles else {}

    async def get_historical_candles(
        self,
        token: str,
        account_id: str,
        symbol: str,
        timeframe: str,
        start_time: datetime = None,
        limit: int = None,
    ) -> list[dict]:
        requested = str(symbol or "").strip()
        mt5_timeframe = self._timeframe(timeframe)
        count = int(limit or 100)

        def operation():
            resolved_symbol = _find_mt5_symbol_name(requested)
            if start_time:
                rates = mt5.copy_rates_from(resolved_symbol, mt5_timeframe, start_time, count)
            else:
                rates = mt5.copy_rates_from_pos(resolved_symbol, mt5_timeframe, 0, count)
            if rates is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 candles available for {resolved_symbol}."))
            return [
                {
                    "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tickVolume": int(row["tick_volume"]),
                    "volume": int(row["tick_volume"]),
                }
                for row in rates
            ]

        return await self._with_session(token, account_id, operation)

    async def get_historical_candles_range(
        self,
        token: str,
        account_id: str,
        symbol: str,
        timeframe: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[dict]:
        requested = str(symbol or "").strip()
        mt5_timeframe = self._timeframe(timeframe)

        def operation():
            resolved_symbol = _find_mt5_symbol_name(requested)
            rates = mt5.copy_rates_range(resolved_symbol, mt5_timeframe, from_time, to_time)
            if rates is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 candles available for {resolved_symbol}."))
            return [
                {
                    "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tickVolume": int(row["tick_volume"]),
                    "volume": int(row["tick_volume"]),
                }
                for row in rates
            ]

        return await self._with_session(token, account_id, operation)

    async def get_symbols(self, token: str, account_id: str) -> List[str]:
        cache_key = str(account_id)
        if cache_key in self._symbols_cache:
            return self._symbols_cache[cache_key]

        def operation():
            symbols = mt5.symbols_get()
            if not symbols:
                return []
            original_by_normalized = {}
            for item in symbols:
                name = str(getattr(item, "name", "") or "").strip()
                if not name:
                    continue
                normalized = normalize_symbol(name)
                if not normalized:
                    continue
                if normalized not in original_by_normalized:
                    original_by_normalized[normalized] = name
            return sorted(original_by_normalized.values(), key=lambda value: value.upper())

        symbols = await self._with_session(token, account_id, operation)
        self._symbols_cache[cache_key] = symbols
        return symbols

    async def get_symbol_specification(self, token: str, account_id: str, symbol: str) -> dict:
        requested = str(symbol or "").strip()
        if not requested:
            raise LocalMT5Error("Symbol is required.")

        def operation():
            resolved_symbol = _find_mt5_symbol_name(requested)
            info = mt5.symbol_info(resolved_symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {resolved_symbol}."))
            data = info._asdict()
            return {
                "symbol": str(getattr(info, "name", None) or resolved_symbol),
                "point": float(data.get("point") or 0),
                "tickSize": float(data.get("trade_tick_size") or data.get("point") or 0),
                "tickValue": float(data.get("trade_tick_value") or 0),
                "tradeTickValue": float(data.get("trade_tick_value") or 0),
                "contractSize": float(data.get("trade_contract_size") or 100000),
                "tradeContractSize": float(data.get("trade_contract_size") or 100000),
                "digits": int(data.get("digits") or 0),
                "volumeMin": float(data.get("volume_min") or 0.01),
                "volumeMax": float(data.get("volume_max") or 100),
                "volumeStep": float(data.get("volume_step") or 0.01),
            }

        return await self._with_session(token, account_id, operation)

    async def get_server_time(self, token: str, account_id: str) -> dict:
        return {
            "time": datetime.now(timezone.utc).isoformat(),
            "brokerTime": datetime.now(timezone.utc).isoformat(),
            "region": "local",
        }

    async def get_risk_context(self, token: str, account_id: str, symbol: str) -> dict:
        account_info = await self.get_account_information(token, account_id)
        symbol_spec = await self.get_symbol_specification(token, account_id, symbol)
        pip_size = pip_size_for_symbol(symbol)
        tick_size = float(symbol_spec.get("tickSize") or symbol_spec.get("point") or 0)
        tick_value = float(symbol_spec.get("tickValue") or symbol_spec.get("tradeTickValue") or 0)
        pip_value = (pip_size / tick_size) * tick_value if symbol_uses_pips(symbol) and tick_size > 0 and tick_value > 0 else 0.0
        return {
            "account_currency": str(account_info.get("currency") or "USD"),
            "pip_size": pip_size,
            "pip_value_per_standard_lot": float(pip_value) if pip_value > 0 else 0.0,
            "tick_size": tick_size,
            "tick_value": tick_value,
            "contract_size": float(symbol_spec.get("contractSize") or symbol_spec.get("tradeContractSize") or 0.0),
            "volume_step": float(symbol_spec.get("volumeStep") or 0.01),
            "volume_min": float(symbol_spec.get("volumeMin") or 0.01),
            "volume_max": float(symbol_spec.get("volumeMax") or 100),
        }

    async def get_trade_history(self, token: str, account_id: str, from_time: datetime, to_time: datetime) -> list[dict]:
        def operation():
            deals = mt5.history_deals_get(from_time, to_time)
            if deals is None:
                raise LocalMT5Error(_last_error_message("MT5 trade history read failed."))
            positions = mt5.positions_get() or []
            return _normalize_trade_history(deals, positions)

        return await self._with_session(token, account_id, operation)

    async def resolve_closed_orders_realized_pl(self, token: str, account_id: str, orders: list[dict]) -> dict[str, float]:
        pending = [order for order in orders if needs_closed_realized_pl_resolution(order)]
        if not pending:
            return {}

        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=90)

        def operation():
            deals = mt5.history_deals_get(from_time, to_time)
            if deals is None:
                return [], []
            positions = mt5.positions_get() or []
            return list(deals), _normalize_trade_history(deals, positions)

        deals, rows = await self._with_session(token, account_id, operation)
        closed_rows = [row for row in (rows or []) if not row.get("is_running")]
        resolved: dict[str, float] = {}

        for order in pending:
            order_key = str(order.get("_id") or order.get("id") or "")
            if not order_key:
                continue
            value = match_order_to_trade_history(order, closed_rows)
            if value is None and deals:
                value = closed_trade_net_profit_from_deals(
                    deals,
                    position_id=str(order.get("meta_position_id") or "") or None,
                    order_id=str(order.get("meta_order_id") or "") or None,
                    symbol=str(order.get("symbol") or "") or None,
                )
            if value is None:
                value = merge_realized_pl_on_close(order)
            if value is None and order.get("last_broker_profit") is not None:
                try:
                    value = round(float(order["last_broker_profit"]), 2)
                except (TypeError, ValueError):
                    value = None
            if value is not None:
                resolved[order_key] = value
        return resolved

    async def resolve_active_orders_booked_pl(self, token: str, account_id: str, orders: list[dict]) -> dict[str, float]:
        pending = [order for order in orders if needs_active_booked_pl_resolution(order)]
        if not pending:
            return {}

        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=90)

        def operation():
            deals = mt5.history_deals_get(from_time, to_time)
            if deals is None:
                return []
            return list(deals)

        deals = await self._with_session(token, account_id, operation)
        if not deals:
            return {}

        resolved: dict[str, float] = {}
        for order in pending:
            order_key = str(order.get("_id") or order.get("id") or "")
            if not order_key:
                continue
            value = booked_profit_from_deals(
                deals,
                position_id=str(order.get("meta_position_id") or "") or None,
                order_id=str(order.get("meta_order_id") or "") or None,
                symbol=str(order.get("symbol") or "") or None,
            )
            if value is not None:
                resolved[order_key] = value
        return resolved

    async def get_position_net_profit(self, token: str, account_id: str, position_id: str, lookback_days: int = 90) -> float | None:
        if not position_id:
            return None
        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(days=max(1, lookback_days))

        def operation():
            deals = mt5.history_deals_get(from_time, to_time)
            if deals is None:
                return None
            return closed_trade_net_profit_from_deals(deals, position_id=position_id)

        return await self._with_session(token, account_id, operation)

    async def place_pending_order(self, token: str, account_id: str, payload: dict) -> dict:
        side = str(payload["side"]).upper()
        order_type = str(payload["order_type"]).upper()
        volume = float(payload["quantity"])

        def operation():
            symbol = _find_mt5_symbol_name(str(payload["symbol"]))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {symbol}."))
            symbol_spec = _symbol_spec_from_info(info)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise LocalMT5Error(_last_error_message(f"No tick available for {symbol}."))
            if order_type == "MARKET":
                mt5_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
                price = tick.ask if side == "BUY" else tick.bid
                action = mt5.TRADE_ACTION_DEAL
            elif order_type == "SL":
                mt5_type = mt5.ORDER_TYPE_BUY_STOP if side == "BUY" else mt5.ORDER_TYPE_SELL_STOP
                price = float(payload["entry"])
                action = mt5.TRADE_ACTION_PENDING
            else:
                mt5_type = mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
                price = float(payload["entry"])
                action = mt5.TRADE_ACTION_PENDING
            normalized_volume = normalize_volume_to_risk(
                volume,
                volume_step=float(symbol_spec.get("volumeStep") or 0.01),
                volume_min=float(symbol_spec.get("volumeMin") or 0.01),
                volume_max=float(symbol_spec.get("volumeMax") or 0),
            )
            if normalized_volume <= 0:
                raise LocalMT5Error(
                    append_order_log_prices(
                        f"MT5 order volume {volume} is below broker minimum/step for {symbol}.",
                        side=side,
                        entry=price,
                        stop_loss=float(payload["stop_loss"]),
                        target=float(payload.get("target") or 0),
                        quantity=volume,
                        bid=float(tick.bid),
                        ask=float(tick.ask),
                    )
                )
            type_filling = _order_filling_mode(info)
            request = {
                "action": action,
                "symbol": symbol,
                "volume": normalized_volume,
                "type": mt5_type,
                "price": _normalize_order_price(price, symbol_spec),
                "sl": _normalize_order_price(float(payload["stop_loss"]), symbol_spec),
                "tp": _normalize_order_price(float(payload.get("target") or 0), symbol_spec),
                "deviation": 20,
                "magic": 20260531,
                "comment": "SignalBridge local MT5",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": type_filling,
            }
            if action == mt5.TRADE_ACTION_PENDING and _symbol_supports_specified_expiration(info):
                request["type_time"] = mt5.ORDER_TIME_SPECIFIED
                request["expiration"] = _mt5_friday_expiration_timestamp(tick)
            result = mt5.order_send(request)
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 order_send returned no result."))
            data = result._asdict()
            if data.get("retcode") not in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}:
                reject_msg = f"MT5 order rejected: retcode={data.get('retcode')} comment={data.get('comment')}"
                if data.get("retcode") == 10030 or "unsupported filling" in str(data.get("comment") or "").lower():
                    reject_msg = f"{reject_msg} · {_filling_mode_diag(info, type_filling)}"
                raise LocalMT5Error(
                    append_order_log_prices(
                        reject_msg,
                        side=side,
                        entry=request["price"],
                        stop_loss=request["sl"],
                        target=request["tp"],
                        quantity=normalized_volume,
                        bid=float(tick.bid),
                        ask=float(tick.ask),
                    )
                )
            order_ticket = data.get("order")
            if action == mt5.TRADE_ACTION_PENDING and not order_ticket:
                raise LocalMT5Error(
                    append_order_log_prices(
                        "MT5 pending order placement returned no order ticket.",
                        side=side,
                        entry=request["price"],
                        stop_loss=request["sl"],
                        target=request["tp"],
                        quantity=normalized_volume,
                        bid=float(tick.bid),
                        ask=float(tick.ask),
                    )
                )
            return {"orderId": str(order_ticket or data.get("deal") or ""), "raw": data}

        return await self._with_session(token, account_id, operation)

    async def cancel_order(self, token: str, account_id: str, order_id: str):
        def operation():
            ticket = int(order_id)
            orders = mt5.orders_get(ticket=ticket) or []
            if not orders:
                return {"already_cancelled": True, "ticket": ticket}
            symbol = _find_mt5_symbol_name(str(orders[0].symbol))
            request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket, "symbol": symbol}
            result = mt5.order_send(request)
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 cancel returned no result."))
            data = result._asdict()
            if data.get("retcode") != mt5.TRADE_RETCODE_DONE:
                still_open = mt5.orders_get(ticket=ticket) or []
                if not still_open:
                    return {"already_cancelled": True, "raw": data}
                raise LocalMT5Error(f"MT5 cancel rejected: retcode={data.get('retcode')} comment={data.get('comment')}")
            return data

        return await self._with_session(token, account_id, operation)

    async def modify_pending_order(
        self,
        token: str,
        account_id: str,
        order_id: str,
        *,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        volume: Optional[float] = None,
    ):
        def operation():
            orders = mt5.orders_get(ticket=int(order_id)) or []
            if not orders:
                raise LocalMT5Error("MT5 pending order not found.")
            symbol = _find_mt5_symbol_name(str(orders[0].symbol))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {symbol}."))
            symbol_spec = _symbol_spec_from_info(info)
            request: dict = {"action": mt5.TRADE_ACTION_MODIFY, "order": int(order_id)}
            if price is not None:
                request["price"] = _normalize_order_price(price, symbol_spec)
            if stop_loss is not None:
                request["sl"] = _normalize_order_price(stop_loss, symbol_spec)
            if target is not None:
                request["tp"] = _normalize_order_price(target or 0, symbol_spec)
            if volume is not None:
                normalized_volume = normalize_volume_to_risk(
                    float(volume),
                    volume_step=float(symbol_spec.get("volumeStep") or 0.01),
                    volume_min=float(symbol_spec.get("volumeMin") or 0.01),
                    volume_max=float(symbol_spec.get("volumeMax") or 0),
                )
                if normalized_volume <= 0:
                    raise LocalMT5Error(f"MT5 order volume {volume} is below broker minimum/step for {symbol}.")
                request["volume"] = normalized_volume
            result = mt5.order_send(request)
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 modify returned no result."))
            data = result._asdict()
            if data.get("retcode") != mt5.TRADE_RETCODE_DONE:
                raise LocalMT5Error(f"MT5 modify rejected: retcode={data.get('retcode')} comment={data.get('comment')}")
            return data

        return await self._with_session(token, account_id, operation)

    async def close_position(self, token: str, account_id: str, position_id: str, volume: float):
        def operation():
            positions = mt5.positions_get(ticket=int(position_id)) or []
            if not positions:
                raise LocalMT5Error("MT5 position not found.")
            position = positions[0]
            symbol = _find_mt5_symbol_name(str(position.symbol))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {symbol}."))
            symbol_spec = _symbol_spec_from_info(info)
            tick = mt5.symbol_info_tick(symbol)
            close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            normalized_volume = normalize_volume_to_risk(
                float(volume),
                volume_step=float(symbol_spec.get("volumeStep") or 0.01),
                volume_min=float(symbol_spec.get("volumeMin") or 0.01),
                volume_max=float(symbol_spec.get("volumeMax") or 0),
            )
            if normalized_volume <= 0:
                raise LocalMT5Error(f"MT5 close volume {volume} is below broker minimum/step for {symbol}.")
            type_filling = _order_filling_mode(info)
            result = mt5.order_send(
                {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": normalized_volume,
                    "type": close_type,
                    "position": int(position.ticket),
                    "price": _normalize_order_price(price, symbol_spec),
                    "deviation": 20,
                    "magic": 20260531,
                    "comment": "SignalBridge close",
                    "type_filling": type_filling,
                }
            )
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 close returned no result."))
            data = result._asdict()
            retcode = data.get("retcode")
            if retcode == 10030 or "unsupported filling" in str(data.get("comment") or "").lower():
                raise LocalMT5Error(
                    f"MT5 close rejected: retcode={retcode} comment={data.get('comment')} · "
                    f"{_filling_mode_diag(info, type_filling)}"
                )
            return data

        return await self._with_session(token, account_id, operation)

    async def close_position_limit(
        self,
        token: str,
        account_id: str,
        position_id: str,
        volume: float,
        price: float,
    ):
        """Place a closing LIMIT pending order linked to an open position."""

        def operation():
            positions = mt5.positions_get(ticket=int(position_id)) or []
            if not positions:
                raise LocalMT5Error("MT5 position not found.")
            position = positions[0]
            symbol = _find_mt5_symbol_name(str(position.symbol))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {symbol}."))
            symbol_spec = _symbol_spec_from_info(info)
            # Long position → sell limit; short position → buy limit
            close_type = mt5.ORDER_TYPE_SELL_LIMIT if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY_LIMIT
            normalized_volume = normalize_volume_to_risk(
                float(volume),
                volume_step=float(symbol_spec.get("volumeStep") or 0.01),
                volume_min=float(symbol_spec.get("volumeMin") or 0.01),
                volume_max=float(symbol_spec.get("volumeMax") or 0),
            )
            if normalized_volume <= 0:
                raise LocalMT5Error(f"MT5 close volume {volume} is below broker minimum/step for {symbol}.")
            normalized_price = _normalize_order_price(float(price), symbol_spec)
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": normalized_volume,
                "type": close_type,
                "position": int(position.ticket),
                "price": normalized_price,
                "magic": 20260531,
                "comment": "SignalBridge partial limit",
                "type_time": mt5.ORDER_TIME_GTC,
            }
            if _symbol_supports_specified_expiration(info):
                tick = mt5.symbol_info_tick(symbol)
                request["type_time"] = mt5.ORDER_TIME_SPECIFIED
                request["expiration"] = _mt5_friday_expiration_timestamp(tick)
            result = mt5.order_send(request)
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 limit close returned no result."))
            data = result._asdict()
            if data.get("retcode") not in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}:
                raise LocalMT5Error(
                    f"MT5 limit close rejected: retcode={data.get('retcode')} comment={data.get('comment')}"
                )
            order_ticket = data.get("order")
            if not order_ticket:
                raise LocalMT5Error("MT5 limit close returned no order ticket.")
            return {"orderId": str(order_ticket), "raw": data, "price": normalized_price, "volume": normalized_volume}

        return await self._with_session(token, account_id, operation)

    async def modify_position(self, token: str, account_id: str, position_id: str, stop_loss: float = None, take_profit: float = None):
        def operation():
            positions = mt5.positions_get(ticket=int(position_id)) or []
            if not positions:
                raise LocalMT5Error("MT5 position not found.")
            symbol = _find_mt5_symbol_name(str(positions[0].symbol))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMT5Error(_last_error_message(f"No MT5 symbol specification for {symbol}."))
            symbol_spec = _symbol_spec_from_info(info)
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": int(position_id),
                "sl": _normalize_order_price(stop_loss or 0, symbol_spec),
                "tp": _normalize_order_price(take_profit or 0, symbol_spec),
            }
            result = mt5.order_send(request)
            if result is None:
                raise LocalMT5Error(_last_error_message("MT5 modify returned no result."))
            return result._asdict()

        return await self._with_session(token, account_id, operation)

    async def get_terminal_state(self, token: str, account_id: str):
        class State:
            orders = []
            positions = []
            read_ok = False

        try:
            def operation():
                State.orders = [self._order_dict(item) for item in (mt5.orders_get() or [])]
                State.positions = [self._position_dict(item) for item in (mt5.positions_get() or [])]

            await self._with_session(token, account_id, operation)
            State.read_ok = True
        except Exception:
            logger.exception("Unable to read local MT5 terminal state")
        return State

    async def _with_session(self, token: str, account_id: str, operation):
        return await self._session_manager.run(token, account_id, operation)

    def _run_session_sync(self, token: str, account_id: str, operation):
        if mt5 is None:
            raise LocalMT5Error("MetaTrader5 package is not installed.")
        credentials = self._decode_credentials(token)
        login = int(account_id)
        server = credentials.get("server") or ""
        path = credentials.get("path") or self._detect_terminal_path()

        # When a terminal path is provided, attach to that already-running MT5
        # instance instead of asking the terminal to log in/switch accounts.
        # Passing login/password here can create/switch account entries inside
        # the terminal, which is not desired for local multi-instance setups.
        kwargs: dict[str, Any] = {"timeout": 60_000}
        if path:
            kwargs["path"] = path
        else:
            kwargs.update(
                {
                    "login": login,
                    "password": credentials.get("password") or "",
                    "server": server,
                }
            )
        if not mt5.initialize(**kwargs):
            raise LocalMT5Error(_last_error_message("MT5 initialize/login failed."))
        try:
            self._assert_connected_account(login, server, path)
            return operation()
        finally:
            mt5.shutdown()

    def _assert_connected_account(self, expected_login: int, expected_server: str, path: str | None) -> None:
        account_info = mt5.account_info()
        if account_info is None:
            raise LocalMT5Error(_last_error_message("MT5 account information unavailable after initialize."))
        data = account_info._asdict()
        actual_login = int(data.get("login") or 0)
        actual_server = str(data.get("server") or "")
        if actual_login != expected_login:
            path_hint = f" Terminal path: {path}" if path else ""
            raise LocalMT5Error(
                "Connected MT5 terminal is logged into a different account "
                f"({actual_login}) than requested ({expected_login})."
                f"{path_hint} Use a separate MT5 installation/copy per account and save that account's terminal64.exe path."
            )
        if expected_server and actual_server and actual_server != expected_server:
            raise LocalMT5Error(
                "Connected MT5 terminal server does not match the saved account "
                f"({actual_server} != {expected_server})."
            )

    def _decode_credentials(self, token: str) -> dict:
        raw = str(token or "")
        try:
            raw = decrypt_secret(raw)
        except Exception:
            pass
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return {
                    "password": str(payload.get("password") or ""),
                    "server": str(payload.get("server") or ""),
                    "path": str(payload.get("path") or ""),
                }
        except Exception:
            pass
        return {"password": raw, "server": "", "path": ""}

    def _detect_terminal_path(self) -> str | None:
        paths = find_running_terminal_paths()
        return paths[0] if paths else None

    def _timeframe(self, timeframe: str):
        normalized = str(timeframe or "1h").lower()
        mapping = {
            "1m": mt5.TIMEFRAME_M1,
            "m1": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "m5": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "m15": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "m30": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "h1": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "h4": mt5.TIMEFRAME_H4,
            "d": mt5.TIMEFRAME_D1,
            "1d": mt5.TIMEFRAME_D1,
            "d1": mt5.TIMEFRAME_D1,
        }
        return mapping.get(normalized, mt5.TIMEFRAME_H1)

    def _order_dict(self, item) -> dict:
        data = item._asdict()
        order_type, side = infer_order_type_and_side({"type": data.get("type")})
        return {
            "id": str(data.get("ticket")),
            "symbol": data.get("symbol"),
            "type": data.get("type"),
            "order_type": order_type,
            "side": side,
            "state": data.get("state"),
            "volume": data.get("volume_initial") or data.get("volume_current"),
            "openPrice": data.get("price_open"),
            "currentPrice": data.get("price_current"),
            "stopLoss": data.get("sl"),
            "takeProfit": data.get("tp"),
        }

    def _position_dict(self, item) -> dict:
        data = item._asdict()
        return {
            "id": str(data.get("ticket")),
            "symbol": data.get("symbol"),
            "type": data.get("type"),
            "time": data.get("time"),
            "timeMsc": data.get("time_msc"),
            "updatedTime": data.get("time_update"),
            "updatedTimeMsc": data.get("time_update_msc"),
            "volume": data.get("volume"),
            "openPrice": data.get("price_open"),
            "currentPrice": data.get("price_current"),
            "stopLoss": data.get("sl"),
            "takeProfit": data.get("tp"),
            "unrealizedProfit": data.get("profit"),
            "profit": data.get("profit"),
        }

    @staticmethod
    def now_ist() -> str:
        return datetime.now(ZoneInfo(settings.timezone)).isoformat()

    @staticmethod
    def serialize_payload(payload: dict) -> str:
        return json.dumps(payload, default=str)


def _timestamp_from_seconds(value) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=ZoneInfo(settings.timezone)).isoformat()


def _deal_id(deal: dict) -> str:
    value = deal.get("ticket")
    return str(value) if value is not None else ""


def _deal_time(deal: dict) -> int:
    try:
        return int(deal.get("time") or 0)
    except (TypeError, ValueError):
        return 0


def _deal_type_label(raw_type) -> str:
    raw = str(raw_type).upper()
    if raw == "1" or "SELL" in raw:
        return "Sell"
    return "Buy"


def _is_trade_deal(deal: dict) -> bool:
    raw = str(deal.get("type")).upper()
    return raw in {"0", "1"} or raw in {"DEAL_TYPE_BUY", "DEAL_TYPE_SELL"} or raw.endswith("_BUY") or raw.endswith("_SELL")


def _is_entry_deal(deal: dict) -> bool:
    raw = str(deal.get("entry")).upper()
    return raw in {"0", "DEAL_ENTRY_IN", "IN"}


def _is_exit_deal(deal: dict) -> bool:
    raw = str(deal.get("entry")).upper()
    return raw in {"1", "2", "3", "DEAL_ENTRY_OUT", "DEAL_ENTRY_INOUT", "DEAL_ENTRY_OUT_BY", "OUT", "INOUT", "OUT_BY"}


def _money_value(deal: dict, key: str) -> float:
    try:
        return float(deal.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def merge_realized_pl_on_close(order: dict) -> float | None:
    try:
        unrealized = order.get("unrealized_pl")
        if unrealized is not None:
            realized = float(order.get("realized_pl") or 0)
            return round(realized + float(unrealized), 2)
    except (TypeError, ValueError):
        pass
    return order.get("realized_pl")


def needs_closed_realized_pl_resolution(order: dict) -> bool:
    if str(order.get("status") or "").upper() != "CLOSED":
        return False
    realized = order.get("realized_pl")
    if realized is None:
        return True
    try:
        if float(realized) != 0.0:
            return False
    except (TypeError, ValueError):
        return True
    return bool(
        order.get("meta_position_id")
        or order.get("meta_order_id")
        or order.get("last_broker_profit") is not None
        or order.get("unrealized_pl") is not None
    )


def _deal_matches_order(deal: dict, *, position_id: str = "", order_id: str = "") -> bool:
    deal_position_id = str(deal.get("position_id") or deal.get("position") or "").strip()
    deal_order_id = str(deal.get("order") or deal.get("ticket") or "").strip()
    target_position_id = str(position_id or "").strip()
    target_order_id = str(order_id or "").strip()
    if target_position_id and deal_position_id == target_position_id:
        return True
    if target_order_id and deal_order_id == target_order_id:
        return True
    if target_position_id and deal_order_id == target_position_id:
        return True
    return False


def order_has_partial_booking(order: dict) -> bool:
    status = str(order.get("status") or "").upper()
    if status == "PARTIALLY_CLOSED":
        return True
    if order.get("gold_partial_booked") or order.get("forex_partial_booked"):
        return True
    manual_context = order.get("manual_context") or {}
    if manual_context.get("partial_booked_4r") or manual_context.get("target_booked"):
        return True
    try:
        quantity = float(order.get("quantity") or 0)
        position_quantity = order.get("position_quantity")
        if position_quantity is not None and quantity > 0 and float(position_quantity) < quantity - 1e-8:
            return True
    except (TypeError, ValueError):
        pass
    return False


def needs_active_booked_pl_resolution(order: dict) -> bool:
    status = str(order.get("status") or "").upper()
    if status not in {"POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED"}:
        return False
    if not order_has_partial_booking(order):
        return False
    if not (order.get("meta_position_id") or order.get("meta_order_id")):
        return False
    realized = order.get("realized_pl")
    if realized is None:
        return True
    try:
        return float(realized) == 0.0
    except (TypeError, ValueError):
        return True


def _matched_deals_for_order(
    deals,
    *,
    position_id: str | None = None,
    order_id: str | None = None,
    symbol: str | None = None,
) -> list[dict]:
    trade_deals = [_normalize_deal(deal) if hasattr(deal, "_asdict") else deal for deal in (deals or [])]
    trade_deals = [deal for deal in trade_deals if isinstance(deal, dict) and _is_trade_deal(deal)]
    if not trade_deals:
        return []

    target_position_id = str(position_id or "").strip()
    target_order_id = str(order_id or "").strip()
    target_symbol = str(symbol or "").upper().strip()

    matched: list[dict] = []
    for deal in trade_deals:
        if _deal_matches_order(deal, position_id=target_position_id, order_id=target_order_id):
            matched.append(deal)

    if not matched and target_position_id:
        groups: dict[str, list[dict]] = {}
        for deal in trade_deals:
            groups.setdefault(_position_group_key(deal), []).append(deal)
        for group_key, group_deals in groups.items():
            if group_key == target_position_id or any(
                _deal_matches_order(deal, position_id=target_position_id, order_id=target_order_id)
                for deal in group_deals
            ):
                matched = group_deals
                break

    if not matched and target_symbol:
        symbol_deals = [deal for deal in trade_deals if str(deal.get("symbol") or "").upper() == target_symbol]
        exit_deals = [deal for deal in symbol_deals if _is_exit_deal(deal)]
        if len(exit_deals) == 1:
            matched = symbol_deals

    return matched


def booked_profit_from_deals(
    deals,
    *,
    position_id: str | None = None,
    order_id: str | None = None,
    symbol: str | None = None,
) -> float | None:
    matched = _matched_deals_for_order(
        deals,
        position_id=position_id,
        order_id=order_id,
        symbol=symbol,
    )
    exit_deals = [deal for deal in matched if _is_exit_deal(deal)]
    if not exit_deals:
        return None
    total = 0.0
    for deal in exit_deals:
        total += (
            _money_value(deal, "profit")
            + _money_value(deal, "commission")
            + _money_value(deal, "fee")
            + _money_value(deal, "swap")
        )
    return round(total, 2)


def closed_trade_net_profit_from_deals(
    deals,
    *,
    position_id: str | None = None,
    order_id: str | None = None,
    symbol: str | None = None,
) -> float | None:
    matched = _matched_deals_for_order(
        deals,
        position_id=position_id,
        order_id=order_id,
        symbol=symbol,
    )
    if not matched:
        return None

    total = 0.0
    for deal in matched:
        total += (
            _money_value(deal, "profit")
            + _money_value(deal, "commission")
            + _money_value(deal, "fee")
            + _money_value(deal, "swap")
        )
    return round(total, 2)


def position_net_profit_from_deals(deals, position_id: str) -> float | None:
    return closed_trade_net_profit_from_deals(deals, position_id=position_id)


def _parse_trade_history_timestamp(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def match_order_to_trade_history(order: dict, closed_rows: list[dict]) -> float | None:
    position_id = str(order.get("meta_position_id") or "").strip()
    order_id = str(order.get("meta_order_id") or "").strip()
    symbol = str(order.get("symbol") or "").upper().strip()
    opened_at = _parse_trade_history_timestamp(order.get("opened_at"))

    for row in closed_rows:
        row_pos = str(row.get("position_id") or "").strip()
        row_order = str(row.get("order_id") or "").strip()
        deal_ids = {str(value).strip() for value in (row.get("deal_ids") or []) if value not in (None, "")}
        if position_id and (row_pos == position_id or position_id in deal_ids):
            return float(row.get("net_profit", row.get("profit", 0)))
        if order_id and (row_pos == order_id or row_order == order_id or order_id in deal_ids):
            return float(row.get("net_profit", row.get("profit", 0)))

    if not symbol or opened_at is None:
        return None

    best_row = None
    best_delta = None
    for row in closed_rows:
        if str(row.get("symbol") or "").upper() != symbol:
            continue
        row_open = _parse_trade_history_timestamp(row.get("open_time"))
        if row_open is None:
            continue
        delta = abs(row_open - opened_at)
        if delta > 3600:
            continue
        if best_delta is None or delta < best_delta:
            best_row = row
            best_delta = delta
    if best_row is not None:
        return float(best_row.get("net_profit", best_row.get("profit", 0)))
    return None


def _normalize_deal(item) -> dict:
    data = item._asdict()
    return data


def _normalize_position(item) -> dict:
    data = item._asdict()
    return data


def _position_group_key(deal: dict) -> str:
    for key in ("position_id", "position", "identifier", "order", "ticket"):
        value = deal.get(key)
        if value not in (None, "", 0):
            return str(value)
    return _deal_id(deal)


def _normalize_trade_history(deals, positions) -> list[dict]:
    trade_deals = [_normalize_deal(deal) for deal in deals if _is_trade_deal(_normalize_deal(deal))]
    groups: dict[str, list[dict]] = {}
    for deal in trade_deals:
        groups.setdefault(_position_group_key(deal), []).append(deal)

    rows: list[dict] = []
    for position_id, position_deals in groups.items():
        ordered = sorted(position_deals, key=_deal_time)
        entry_deals = [deal for deal in ordered if _is_entry_deal(deal)]
        exit_deals = [deal for deal in ordered if _is_exit_deal(deal)]
        open_deal = entry_deals[0] if entry_deals else ordered[0]
        symbol = str(open_deal.get("symbol") or "").upper()
        side = _deal_type_label(open_deal.get("type"))
        open_price = float(open_deal.get("price") or 0.0)
        open_time = _timestamp_from_seconds(open_deal.get("time"))

        for exit_deal in exit_deals:
            profit = _money_value(exit_deal, "profit")
            commission = _money_value(exit_deal, "commission") + _money_value(exit_deal, "fee")
            swap = _money_value(exit_deal, "swap")
            net_profit = profit + commission + swap
            deal_id = _deal_id(exit_deal)
            rows.append(
                {
                    "id": f"closed:{position_id}:{deal_id}",
                    "position_id": position_id,
                    "order_id": str(exit_deal.get("order")) if exit_deal.get("order") is not None else None,
                    "deal_ids": [_deal_id(open_deal), deal_id],
                    "symbol": symbol or str(exit_deal.get("symbol") or "").upper(),
                    "type": side,
                    "status": "CLOSED",
                    "open_time": open_time,
                    "open_price": open_price,
                    "close_time": _timestamp_from_seconds(exit_deal.get("time")),
                    "close_price": float(exit_deal.get("price") or 0.0),
                    "profit": round(profit, 2),
                    "lots": float(exit_deal.get("volume") or 0.0),
                    "commission": round(commission, 2),
                    "swap": round(swap, 2),
                    "net_profit": round(net_profit, 2),
                    "is_running": False,
                }
            )

    for item in positions:
        position = _normalize_position(item)
        position_id = str(position.get("ticket") or position.get("identifier") or "")
        if not position_id:
            continue
        position_deals = groups.get(position_id, [])
        ordered_position_deals = sorted(position_deals, key=_deal_time)
        entry_deals = [deal for deal in ordered_position_deals if _is_entry_deal(deal)]
        open_deal = entry_deals[0] if entry_deals else None
        commission = sum(_money_value(deal, "commission") + _money_value(deal, "fee") for deal in position_deals)
        profit = float(position.get("profit") or 0.0)
        swap = float(position.get("swap") or 0.0)
        rows.append(
            {
                "id": f"running:{position_id}",
                "position_id": position_id,
                "order_id": None,
                "deal_ids": [_deal_id(deal) for deal in position_deals if _deal_id(deal)],
                "symbol": str(position.get("symbol") or "").upper(),
                "type": _deal_type_label(open_deal.get("type") if open_deal else position.get("type")),
                "status": "RUNNING",
                "open_time": _timestamp_from_seconds(open_deal.get("time") if open_deal else position.get("time")),
                "open_price": float((open_deal or {}).get("price") or position.get("price_open") or 0.0),
                "close_time": None,
                "close_price": float(position.get("price_current") or 0.0),
                "profit": round(profit, 2),
                "lots": float(position.get("volume") or 0.0),
                "commission": round(commission, 2),
                "swap": round(swap, 2),
                "net_profit": round(profit + commission + swap, 2),
                "is_running": True,
            }
        )

    return sorted(rows, key=lambda row: row.get("close_time") or row.get("open_time") or "", reverse=True)


metaapi_service = MetaApiService()
