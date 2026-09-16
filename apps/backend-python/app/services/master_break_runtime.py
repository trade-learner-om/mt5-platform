from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from .candle_history import TIMEFRAME_SECONDS, normalize_timeframe
from .master_break_fsm import MasterBreakEvent, MasterBreakSideFSM, SideState
from .master_break_levels import CandleLike, coerce_candle_time, completed_master_bars
from .master_break_persistence import STATUS_RUNNING, mark_stopped, save_run, update_run
from .master_break_risk import quantity_from_risk
from .master_break_settings import STRATEGY_TYPE, MasterBreakSettings
from .metaapi_client import metaapi_service
from .order_placement import place_pending_order_with_limit_fallback
from .risk import digits_from_symbol_spec, normalize_price_to_symbol, point_size_from_symbol_spec
from .symbol_resolver import is_gold_request, normalize_symbol

logger = logging.getLogger(__name__)


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
class MasterBreakRun:
    user_id: str
    account: dict
    requested_symbol: str
    broker_symbol: str
    display_symbol: str
    settings: MasterBreakSettings
    point_size: float
    price_digits: int = 5
    run_id: Optional[ObjectId] = None
    short: MasterBreakSideFSM = field(init=False)
    long: MasterBreakSideFSM = field(init=False)
    master_bars: deque[dict] = field(default_factory=lambda: deque(maxlen=64))
    recent_exec: deque[ExecCandle] = field(default_factory=lambda: deque(maxlen=16))
    current_exec: Optional[ExecCandle] = None
    live_bid: Optional[float] = None
    live_ask: Optional[float] = None
    last_tick_at: Optional[datetime] = None
    last_error: Optional[str] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.short = MasterBreakSideFSM(side="SHORT", settings=self.settings, point=self.point_size)
        self.long = MasterBreakSideFSM(side="LONG", settings=self.settings, point=self.point_size)

    def seed_master(self, candles: list[dict]) -> None:
        completed = completed_master_bars(
            candles,
            timeframe=self.settings.master_timeframe,
            drop_in_progress=True,
        )
        self.master_bars.clear()
        for candle in completed[-64:]:
            self.master_bars.append(dict(candle))
        previous = None
        for candle in self.master_bars:
            self.short.process_master_close(candle, previous)
            self.long.process_master_close(candle, previous)
            previous = candle

    def seed_exec(self, candles: list[dict]) -> None:
        sorted_candles = sorted(candles or [], key=lambda item: str(item.get("time") or ""))
        if not sorted_candles:
            return
        closed = sorted_candles[:-1] if len(sorted_candles) > 1 else []
        for candle in closed[-16:]:
            start = coerce_candle_time(candle.get("time"))
            if not start:
                continue
            bar = ExecCandle(
                start=self._bar_start(start),
                open=float(candle.get("open") or 0.0),
                high=float(candle.get("high") or 0.0),
                low=float(candle.get("low") or 0.0),
                close=float(candle.get("close") or 0.0),
            )
            self.recent_exec.append(bar)
            self.short.process_exec_close(bar.as_dict())
            self.long.process_exec_close(bar.as_dict())
        current = sorted_candles[-1]
        start = coerce_candle_time(current.get("time"))
        if start:
            self.current_exec = ExecCandle(
                start=self._bar_start(start),
                open=float(current.get("open") or 0.0),
                high=float(current.get("high") or 0.0),
                low=float(current.get("low") or 0.0),
                close=float(current.get("close") or 0.0),
            )

    def _bar_start(self, value: datetime) -> datetime:
        seconds = TIMEFRAME_SECONDS[normalize_timeframe(self.settings.exec_timeframe)]
        face = coerce_candle_time(value) or value.replace(tzinfo=None)
        # Align on broker-face epoch (UTC-labeled), never shift via local astimezone.
        ts = int(datetime(face.year, face.month, face.day, face.hour, face.minute, face.second, tzinfo=timezone.utc).timestamp())
        aligned = (ts // seconds) * seconds
        return datetime.fromtimestamp(aligned, tz=timezone.utc).replace(tzinfo=None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id) if self.run_id else None,
            "strategy_type": STRATEGY_TYPE,
            "symbol": self.broker_symbol,
            "requested_symbol": self.requested_symbol,
            "display_symbol": self.display_symbol,
            "settings": self.settings.to_dict(),
            "point_size": self.point_size,
            "price_digits": self.price_digits,
            "live_bid": self.live_bid,
            "live_ask": self.live_ask,
            "last_tick_at": self.last_tick_at.isoformat().replace("+00:00", "Z") if self.last_tick_at else None,
            "last_error": self.last_error,
            "short": self.short.snapshot(),
            "long": self.long.snapshot(),
            "account_id": str(self.account.get("_id") or self.account.get("account_id") or ""),
            "user_id": self.user_id,
        }

    def persistence_doc(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "user_id": ObjectId(self.user_id) if ObjectId.is_valid(str(self.user_id)) else self.user_id,
            "account_id": self.account.get("_id"),
            "account": {
                "account_id": self.account.get("account_id"),
                "_id": self.account.get("_id"),
                "account_currency": self.account.get("account_currency"),
            },
            "requested_symbol": self.requested_symbol,
            "broker_symbol": self.broker_symbol,
            "display_symbol": self.display_symbol,
            "settings": self.settings.to_dict(),
            "point_size": self.point_size,
            "price_digits": self.price_digits,
            "status": STATUS_RUNNING,
            "snapshot": snap,
            "strategy_type": STRATEGY_TYPE,
        }


class MasterBreakManager:
    _instance: Optional["MasterBreakManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.active_runs: dict[str, MasterBreakRun] = {}

    @classmethod
    def instance(cls) -> "MasterBreakManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start_run(
        self,
        *,
        user_id: str,
        account: dict,
        requested_symbol: str,
        broker_symbol: str,
        display_symbol: str,
        settings: MasterBreakSettings | dict,
        master_candles: list[dict],
        exec_candles: list[dict],
        point_size: float,
        price_digits: int = 5,
        db=None,
        run_id: Optional[ObjectId] = None,
    ) -> dict:
        if not is_gold_request(requested_symbol) and not is_gold_request(broker_symbol):
            raise ValueError("Master Break supports XAUUSD/GOLD only")
        cfg = settings if isinstance(settings, MasterBreakSettings) else MasterBreakSettings.from_mapping(settings)
        run = MasterBreakRun(
            user_id=str(user_id),
            account=account,
            requested_symbol=normalize_symbol(requested_symbol),
            broker_symbol=normalize_symbol(broker_symbol),
            display_symbol=display_symbol or broker_symbol,
            settings=cfg,
            point_size=float(point_size),
            price_digits=int(price_digits),
            run_id=run_id,
        )
        run.seed_master(master_candles)
        run.seed_exec(exec_candles)
        if db is not None and run.run_id is None:
            run.run_id = save_run(db, run.persistence_doc())
        elif db is not None and run.run_id is not None:
            update_run(db, run.run_id, run.persistence_doc())

        key = self._run_key(run.broker_symbol, run.user_id, run.account.get("_id"))
        with self._lock:
            self.active_runs[key] = run
        return run.snapshot()

    def stop_run(self, symbol: str, user_id: Optional[str] = None, account_db_id=None, db=None) -> dict:
        key_symbol = normalize_symbol(symbol)
        removed = False
        with self._lock:
            keys = [
                key
                for key, run in self.active_runs.items()
                if normalize_symbol(run.broker_symbol) == key_symbol
                and (not user_id or run.user_id == str(user_id))
                and (account_db_id is None or str(run.account.get("_id") or "") == str(account_db_id))
            ]
            for key in keys:
                run = self.active_runs.pop(key, None)
                if run and db is not None and run.run_id is not None:
                    mark_stopped(db, run.run_id)
                removed = removed or bool(run)
        return {"ok": True, "removed": removed, "symbol": key_symbol}

    def active_symbols(self, user_id: str, account_db_id=None) -> set[str]:
        account_key = str(account_db_id or "")
        with self._lock:
            return {
                run.broker_symbol
                for run in self.active_runs.values()
                if run.user_id == str(user_id)
                and (not account_key or str(run.account.get("_id") or "") == account_key)
            }

    def active_account_ids(self, user_id: str) -> set:
        with self._lock:
            return {
                run.account.get("_id")
                for run in self.active_runs.values()
                if run.user_id == str(user_id) and run.account.get("_id") is not None
            }

    def snapshot_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            items = [run.snapshot() for run in self.active_runs.values() if run.user_id == str(user_id)]
        items.sort(key=lambda item: str(item.get("display_symbol") or item.get("symbol") or ""))
        return items

    def restore(self, db, *, load_account) -> int:
        """Restore RUNNING runs from persistence. `load_account(user_id, account_id)` returns account dict."""
        from .master_break_persistence import list_running_runs

        restored = 0
        for doc in list_running_runs(db):
            try:
                account = load_account(doc.get("user_id"), doc.get("account_id"))
                if not account:
                    continue
                snap = doc.get("snapshot") or {}
                settings = MasterBreakSettings.from_mapping(doc.get("settings") or snap.get("settings"))
                run = MasterBreakRun(
                    user_id=str(doc.get("user_id")),
                    account=account,
                    requested_symbol=normalize_symbol(doc.get("requested_symbol") or "XAUUSD"),
                    broker_symbol=normalize_symbol(doc.get("broker_symbol") or "XAUUSD"),
                    display_symbol=str(doc.get("display_symbol") or doc.get("broker_symbol") or "XAUUSD"),
                    settings=settings,
                    point_size=float(doc.get("point_size") or 0.01),
                    price_digits=int(doc.get("price_digits") or 5),
                    run_id=doc.get("_id"),
                )
                if snap.get("short"):
                    run.short.restore(snap.get("short"))
                if snap.get("long"):
                    run.long.restore(snap.get("long"))
                key = self._run_key(run.broker_symbol, run.user_id, run.account.get("_id"))
                with self._lock:
                    self.active_runs[key] = run
                restored += 1
            except Exception as exc:
                logger.warning("Failed to restore master_break run %s: %s", doc.get("_id"), exc)
        return restored

    async def handle_price(self, symbol: str, tick: dict, db=None) -> None:
        key_symbol = normalize_symbol(symbol)
        with self._lock:
            runs = [run for run in self.active_runs.values() if normalize_symbol(run.broker_symbol) == key_symbol]
        for run in runs:
            await self._on_tick(run, tick, db=db)

    async def ingest_master_close(self, symbol: str, candle: CandleLike, db=None) -> None:
        key_symbol = normalize_symbol(symbol)
        with self._lock:
            runs = [run for run in self.active_runs.values() if normalize_symbol(run.broker_symbol) == key_symbol]
        for run in runs:
            async with run.lock:
                previous = run.master_bars[-1] if run.master_bars else None
                run.master_bars.append(dict(candle))
                for fsm in (run.short, run.long):
                    fsm.process_master_close(candle, previous)
                self._persist(run, db)

    async def _on_tick(self, run: MasterBreakRun, tick: dict, db=None) -> None:
        async with run.lock:
            bid = _safe_float(tick.get("bid"))
            ask = _safe_float(tick.get("ask"))
            price = bid if bid is not None else _safe_float(tick.get("price")) or ask
            if price is None:
                return
            tick_time = coerce_candle_time(tick.get("time")) or datetime.now(timezone.utc).replace(tzinfo=None)
            run.live_bid = price
            run.live_ask = ask
            run.last_tick_at = tick_time

            completed = self._roll_exec(run, price, tick_time)
            if completed is not None:
                await self._handle_exec_close(run, completed, db=db)

            for fsm in (run.short, run.long):
                events = fsm.process_tick(price, ask, high=price, low=price)
                await self._apply_events(run, fsm, events, db=db)
            self._persist(run, db)

    def _roll_exec(self, run: MasterBreakRun, price: float, tick_time: datetime) -> Optional[ExecCandle]:
        bar_start = run._bar_start(tick_time)
        if run.current_exec is None:
            run.current_exec = ExecCandle(start=bar_start, open=price, high=price, low=price, close=price)
            return None
        if run.current_exec.start == bar_start:
            run.current_exec.update(price)
            return None
        completed = run.current_exec
        run.recent_exec.append(completed)
        run.current_exec = ExecCandle(start=bar_start, open=price, high=price, low=price, close=price)
        return completed

    async def _handle_exec_close(self, run: MasterBreakRun, candle: ExecCandle, db=None) -> None:
        for fsm in (run.short, run.long):
            events = fsm.process_exec_close(candle.as_dict(), price_for_limit_check=run.live_bid)
            await self._apply_events(run, fsm, events, db=db)

    async def _apply_events(self, run: MasterBreakRun, fsm: MasterBreakSideFSM, events: list[MasterBreakEvent], db=None) -> None:
        for event in events:
            try:
                if event.type == "ARM_PENDING":
                    await self._place_pending(run, fsm, event)
                elif event.type == "INVALIDATE_PENDING":
                    await self._cancel_pending(run, event.payload.get("order_id"))
                elif event.type == "MOVE_BREAKEVEN":
                    await self._modify_sl(run, fsm, float(event.payload.get("stop_loss") or fsm.entry or 0.0))
                elif event.type == "PARTIAL_EXIT":
                    await self._partial_close(run, fsm, float(event.payload.get("qty") or 0.0))
                elif event.type in {"STOPPED_OUT", "TRADE_CLOSED", "FILLED"}:
                    pass
            except Exception as exc:
                run.last_error = str(exc)
                logger.exception("Master Break event %s failed for %s", event.type, run.broker_symbol)

    async def _place_pending(self, run: MasterBreakRun, fsm: MasterBreakSideFSM, event: MasterBreakEvent) -> None:
        entry = normalize_price_to_symbol(float(event.payload["entry"]), {"digits": run.price_digits, "point": run.point_size})
        stop_loss = normalize_price_to_symbol(
            float(event.payload["stop_loss"]),
            {"digits": run.price_digits, "point": run.point_size},
        )
        try:
            symbol_spec = await metaapi_service.get_symbol_specification(
                run.account["api_token"],
                run.account["account_id"],
                run.broker_symbol,
            )
            run.price_digits = digits_from_symbol_spec(symbol_spec)
            detected_point = point_size_from_symbol_spec(symbol_spec)
            if detected_point > 0:
                run.point_size = detected_point
                fsm.point = detected_point
        except Exception:
            symbol_spec = {"symbol": run.broker_symbol, "digits": run.price_digits, "point": run.point_size}

        try:
            risk_ctx = await metaapi_service.get_risk_context(
                run.account["api_token"],
                run.account["account_id"],
                run.broker_symbol,
            )
        except Exception:
            risk_ctx = None

        quantity = quantity_from_risk(
            run.settings.risk_amount,
            entry,
            stop_loss,
            symbol_spec=symbol_spec,
            live_ctx=risk_ctx,
            symbol=run.broker_symbol,
            account_currency=str(run.account.get("account_currency") or "USD"),
        )
        if quantity <= 0:
            fsm.state = SideState.WAIT_SIGNAL
            fsm.entry = None
            fsm.stop_loss = None
            fsm.signal_extreme = None
            run.last_error = "Risk amount is too small for broker minimum volume."
            return

        side = "SELL" if fsm.side == "SHORT" else "BUY"
        payload = {
            "symbol": run.broker_symbol,
            "order_type": "SL",
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "quantity": quantity,
        }
        placement = await place_pending_order_with_limit_fallback(
            metaapi_service,
            run.account["api_token"],
            run.account["account_id"],
            payload,
        )
        result = placement.get("result") or {}
        order_id = str(result.get("orderId") or result.get("id") or "")
        fill_mode = "LIMIT" if str(placement.get("order_type") or "").upper() == "LIMIT" else "STOP"
        fsm.mark_pending_placed(order_id, quantity, fill_mode=fill_mode)
        fsm.entry = entry
        fsm.stop_loss = stop_loss
        run.last_error = None

    async def _cancel_pending(self, run: MasterBreakRun, order_id: Optional[str]) -> None:
        if not order_id:
            return
        await metaapi_service.cancel_order(run.account["api_token"], run.account["account_id"], str(order_id))

    async def _modify_sl(self, run: MasterBreakRun, fsm: MasterBreakSideFSM, stop_loss: float) -> None:
        position_id = fsm.position_id
        if not position_id:
            return
        await metaapi_service.modify_position(
            run.account["api_token"],
            run.account["account_id"],
            str(position_id),
            stop_loss=stop_loss,
        )

    async def _partial_close(self, run: MasterBreakRun, fsm: MasterBreakSideFSM, qty: float) -> None:
        position_id = fsm.position_id
        if not position_id or qty <= 0:
            return
        await metaapi_service.close_position(
            run.account["api_token"],
            run.account["account_id"],
            str(position_id),
            float(qty),
        )

    def _persist(self, run: MasterBreakRun, db) -> None:
        if db is None or run.run_id is None:
            return
        try:
            update_run(db, run.run_id, {"snapshot": run.snapshot(), "status": STATUS_RUNNING})
        except Exception as exc:
            logger.debug("master_break persist failed: %s", exc)

    @staticmethod
    def _run_key(symbol: str, user_id: str, account_db_id) -> str:
        return f"{normalize_symbol(symbol)}::{user_id}::{account_db_id or ''}"


def _safe_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


master_break_manager = MasterBreakManager.instance()
