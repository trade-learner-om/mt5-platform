from __future__ import annotations

import asyncio
import threading
from bisect import bisect_left, bisect_right
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .metaapi_client import metaapi_service
from .order_placement import place_pending_order_with_limit_fallback
from .risk import (
    calc_quantity,
    calc_quantity_from_live_pip_value,
    digits_from_symbol_spec,
    normalize_price_to_symbol,
    point_size_from_symbol_spec,
)
from .symbol_resolver import normalize_symbol


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "time" not in frame.columns:
        raise ValueError("time column is required")
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time", "high", "low"]).sort_values("time").reset_index(drop=True)
    if frame.empty:
        raise ValueError("at least one candle is required")
    return frame


def index_h1_levels(df: pd.DataFrame) -> tuple[list[float], list[float]]:
    frame = _prepare_dataframe(df)
    highs = frame["high"].astype(float).to_numpy()
    lows = frame["low"].astype(float).to_numpy()
    if len(frame) < 5:
        return [], []

    high_peaks, _ = find_peaks(highs, distance=2)
    low_peaks, _ = find_peaks(-lows, distance=2)
    high_peak_set = set(int(index) for index in high_peaks.tolist())
    low_peak_set = set(int(index) for index in low_peaks.tolist())

    active_supports: list[float] = []
    active_resistances: list[float] = []

    for idx, row in enumerate(frame.itertuples(index=False)):
        high = float(row.high)
        low = float(row.low)
        while active_resistances and high > active_resistances[-1]:
            active_resistances.pop()
        while active_supports and low < active_supports[-1]:
            active_supports.pop()

        if idx in high_peak_set:
            active_resistances.append(high)
        if idx in low_peak_set:
            active_supports.append(low)

    supports = sorted({round(price, 10) for price in active_supports})
    resistances = sorted({round(price, 10) for price in active_resistances})
    return supports, resistances


@dataclass
class M1Candle:
    start: datetime
    open: float
    high: float
    low: float
    close: float

    def update(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    @property
    def bullish(self) -> bool:
        return self.close > self.open


@dataclass
class DoubleTrapFSM:
    user_id: str
    account: dict
    requested_symbol: str
    broker_symbol: str
    display_symbol: str
    risk_amount: float
    active_h1_supports: list[float]
    active_h1_resistances: list[float]
    price_digits: int = 5
    point_size: float = 0.0
    state: str = "SEEKING_H1_SPIKE"
    recent_candles: deque[M1Candle] = field(default_factory=lambda: deque(maxlen=8))
    current_candle: Optional[M1Candle] = None
    current_support_index: Optional[int] = None
    initial_spike_low: Optional[float] = None
    trap_target_high: Optional[float] = None
    current_absolute_low: Optional[float] = None
    true_breakout_high: Optional[float] = None
    last_local_swing_high: Optional[float] = None
    live_bid: Optional[float] = None
    live_ask: Optional[float] = None
    volume: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    placed_order_id: Optional[str] = None
    placement_status: Optional[str] = None
    last_error: Optional[str] = None
    last_tick_at: Optional[datetime] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def seed_m1_history(self, candles: list[dict]) -> None:
        sorted_candles = sorted(candles or [], key=lambda item: str(item.get("time") or ""))
        if not sorted_candles:
            return
        closed_candles = sorted_candles[:-1] if len(sorted_candles) > 1 else []
        for candle in closed_candles[-8:]:
            start = _coerce_tick_time(candle.get("time"))
            if not start:
                continue
            self.recent_candles.append(
                M1Candle(
                    start=_minute_start(start),
                    open=float(candle.get("open") or 0.0),
                    high=float(candle.get("high") or 0.0),
                    low=float(candle.get("low") or 0.0),
                    close=float(candle.get("close") or 0.0),
                )
            )
        current = sorted_candles[-1]
        current_start = _coerce_tick_time(current.get("time"))
        if current_start:
            self.current_candle = M1Candle(
                start=_minute_start(current_start),
                open=float(current.get("open") or 0.0),
                high=float(current.get("high") or 0.0),
                low=float(current.get("low") or 0.0),
                close=float(current.get("close") or 0.0),
            )

    async def on_tick(self, tick: dict) -> None:
        async with self.lock:
            bid = _safe_float(tick.get("bid"))
            ask = _safe_float(tick.get("ask"))
            live_bid = bid if bid is not None else _safe_float(tick.get("price")) or ask
            if live_bid is None:
                return

            tick_time = _coerce_tick_time(tick.get("time")) or datetime.now(timezone.utc)
            self.live_bid = live_bid
            self.live_ask = ask
            self.last_tick_at = tick_time
            await self._roll_m1_candles(live_bid, tick_time)
            await self._advance(live_bid)

    async def _roll_m1_candles(self, price: float, tick_time: datetime) -> None:
        minute_start = _minute_start(tick_time)
        if self.current_candle is None:
            self.current_candle = M1Candle(start=minute_start, open=price, high=price, low=price, close=price)
            return
        if self.current_candle.start == minute_start:
            self.current_candle.update(price)
            return

        completed = self.current_candle
        self.recent_candles.append(completed)
        self.current_candle = M1Candle(start=minute_start, open=price, high=price, low=price, close=price)
        self._process_completed_candle()

    def _process_completed_candle(self) -> None:
        if len(self.recent_candles) < 3:
            return
        left = self.recent_candles[-3]
        middle = self.recent_candles[-2]
        right = self.recent_candles[-1]
        is_local_swing_high = middle.high > left.high and middle.high > right.high and middle.bullish
        if not is_local_swing_high:
            return

        swing_high = float(middle.high)
        self.last_local_swing_high = swing_high
        if self.state == "WAITING_FOR_FIRST_PULLBACK":
            self.trap_target_high = swing_high
            self.state = "WAITING_FOR_TRAP_DROP"
            self.last_error = None
            return
        if self.state == "TRACKING_TRUE_CHOCH":
            self.true_breakout_high = swing_high
            self.state = "WAITING_FOR_BREAKOUT"
            return
        if self.state == "WAITING_FOR_TRAP_DROP":
            self.last_local_swing_high = swing_high

    async def _advance(self, live_bid: float) -> None:
        if self.state == "SEEKING_H1_SPIKE":
            self._seek_h1_spike(live_bid)
            return

        if self.state == "WAITING_FOR_FIRST_PULLBACK":
            if self.initial_spike_low is None or live_bid < self.initial_spike_low:
                self.initial_spike_low = live_bid
            return

        if self.state == "WAITING_FOR_TRAP_DROP":
            if self.trap_target_high is not None and live_bid > self.trap_target_high:
                self.reset()
                return
            if self.initial_spike_low is not None and live_bid < self.initial_spike_low:
                self.current_absolute_low = live_bid
                self.state = "TRACKING_TRUE_CHOCH"
                if self.last_local_swing_high is not None:
                    self.true_breakout_high = self.last_local_swing_high
                    self.state = "WAITING_FOR_BREAKOUT"
                return
            return

        if self.state == "TRACKING_TRUE_CHOCH":
            if self.current_absolute_low is None or live_bid < self.current_absolute_low:
                self.current_absolute_low = live_bid
            return

        if self.state == "WAITING_FOR_BREAKOUT":
            next_support = self._next_deeper_support()
            if next_support is not None and live_bid <= next_support:
                self.current_support_index = max(0, (self.current_support_index or 0) - 1)
                self.initial_spike_low = live_bid
                self.current_absolute_low = live_bid
                self.trap_target_high = None
                self.true_breakout_high = None
                self.last_local_swing_high = None
                self.state = "WAITING_FOR_FIRST_PULLBACK"
                return
            if self.true_breakout_high is not None and live_bid >= self.true_breakout_high:
                await self._execute()
            return

    def _seek_h1_spike(self, live_bid: float) -> None:
        if not self.active_h1_supports:
            return
        index = bisect_left(self.active_h1_supports, live_bid)
        if index >= len(self.active_h1_supports):
            return
        closest_support = self.active_h1_supports[index]
        if live_bid <= closest_support:
            self.current_support_index = index
            self.initial_spike_low = live_bid
            self.current_absolute_low = live_bid
            self.trap_target_high = None
            self.true_breakout_high = None
            self.last_local_swing_high = None
            self.state = "WAITING_FOR_FIRST_PULLBACK"
            self.last_error = None

    def _next_deeper_support(self) -> Optional[float]:
        if self.current_support_index is None or self.current_support_index <= 0:
            return None
        return self.active_h1_supports[self.current_support_index - 1]

    async def _execute(self) -> None:
        if self.placed_order_id:
            self.state = "EXECUTION"
            return

        self.state = "EXECUTION"
        try:
            symbol_spec = await metaapi_service.get_symbol_specification(
                self.account["api_token"],
                self.account["account_id"],
                self.broker_symbol,
            )
            self.price_digits = digits_from_symbol_spec(symbol_spec)
            self.point_size = point_size_from_symbol_spec(symbol_spec)
            if self.point_size <= 0:
                raise ValueError("Broker point size is unavailable.")
            if self.current_absolute_low is None or self.true_breakout_high is None:
                raise ValueError("Breakout context is incomplete.")

            entry_price = normalize_price_to_symbol(self.true_breakout_high, symbol_spec)
            stop_loss = normalize_price_to_symbol(self.current_absolute_low - self.point_size, symbol_spec)
            if stop_loss >= entry_price:
                stop_loss = normalize_price_to_symbol(self.current_absolute_low - (self.point_size * 2), symbol_spec)
            resistance_index = bisect_right(self.active_h1_resistances, entry_price)
            if resistance_index >= len(self.active_h1_resistances):
                raise ValueError("No active H1 resistance is available above the planned entry.")
            target_price = normalize_price_to_symbol(self.active_h1_resistances[resistance_index], symbol_spec)

            try:
                risk_ctx = await metaapi_service.get_risk_context(
                    self.account["api_token"],
                    self.account["account_id"],
                    self.broker_symbol,
                )
            except Exception:
                risk_ctx = None

            volume = 0.0
            if risk_ctx:
                volume = calc_quantity_from_live_pip_value(
                    self.broker_symbol,
                    self.risk_amount,
                    entry_price,
                    stop_loss,
                    risk_ctx["pip_value_per_standard_lot"],
                    volume_step=float(risk_ctx.get("volume_step") or 0.01),
                    volume_min=float(risk_ctx.get("volume_min") or 0.01),
                    volume_max=float(risk_ctx.get("volume_max") or 0),
                    tick_size=float(risk_ctx.get("tick_size") or 0.0),
                    tick_value=float(risk_ctx.get("tick_value") or 0.0),
                    contract_size=float(risk_ctx.get("contract_size") or 0.0),
                    account_currency=str(risk_ctx.get("account_currency") or self.account.get("account_currency") or "USD"),
                )
            if volume <= 0:
                volume = calc_quantity(
                    self.broker_symbol,
                    self.risk_amount,
                    entry_price,
                    stop_loss,
                    account_currency=str(self.account.get("account_currency") or "USD"),
                )
            if volume <= 0:
                raise ValueError("Risk amount is too small for broker minimum volume.")

            placement = await place_pending_order_with_limit_fallback(
                metaapi_service,
                self.account["api_token"],
                self.account["account_id"],
                {
                    "symbol": self.broker_symbol,
                    "order_type": "LIMIT",
                    "side": "BUY",
                    "entry": entry_price,
                    "stop_loss": stop_loss,
                    "target": target_price,
                    "quantity": volume,
                },
            )

            result = placement.get("result") or {}
            self.volume = volume
            self.entry_price = entry_price
            self.stop_loss = stop_loss
            self.target_price = target_price
            self.placed_order_id = str(result.get("orderId") or result.get("id") or "")
            self.placement_status = str(placement.get("order_type") or "LIMIT")
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)

    def reset(self) -> None:
        self.state = "SEEKING_H1_SPIKE"
        self.current_support_index = None
        self.initial_spike_low = None
        self.trap_target_high = None
        self.current_absolute_low = None
        self.true_breakout_high = None
        self.last_local_swing_high = None

    def snapshot(self) -> dict:
        return {
            "symbol": self.broker_symbol,
            "requested_symbol": self.requested_symbol,
            "display_symbol": self.display_symbol,
            "state": self.state,
            "risk_amount": self.risk_amount,
            "volume": self.volume,
            "entry": self.entry_price,
            "stop_loss": self.stop_loss,
            "target": self.target_price,
            "price_digits": self.price_digits,
            "point_size": self.point_size,
            "live_bid": self.live_bid,
            "last_tick_at": self.last_tick_at.isoformat().replace("+00:00", "Z") if self.last_tick_at else None,
            "last_error": self.last_error,
            "placed_order_id": self.placed_order_id,
            "supports": list(self.active_h1_supports),
            "resistances": list(self.active_h1_resistances),
        }


class TrapReversalManager:
    _instance: Optional["TrapReversalManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.active_runs: dict[str, DoubleTrapFSM] = {}

    @classmethod
    def instance(cls) -> "TrapReversalManager":
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
        risk_amount: float,
        supports: list[float],
        resistances: list[float],
        m1_candles: list[dict],
        price_digits: int,
        point_size: float,
    ) -> dict:
        fsm = DoubleTrapFSM(
            user_id=user_id,
            account=account,
            requested_symbol=normalize_symbol(requested_symbol),
            broker_symbol=normalize_symbol(broker_symbol),
            display_symbol=display_symbol,
            risk_amount=float(risk_amount),
            active_h1_supports=supports,
            active_h1_resistances=resistances,
            price_digits=price_digits,
            point_size=point_size,
        )
        fsm.seed_m1_history(m1_candles)
        key = normalize_symbol(broker_symbol)
        with self._lock:
            self.active_runs[key] = fsm
        return fsm.snapshot()

    def stop_run(self, symbol: str, user_id: Optional[str] = None) -> dict:
        key = normalize_symbol(symbol)
        with self._lock:
            fsm = self.active_runs.get(key)
            if not fsm:
                return {"ok": True, "removed": False}
            if user_id and fsm.user_id != user_id:
                return {"ok": False, "removed": False}
            self.active_runs.pop(key, None)
        return {"ok": True, "removed": True, "symbol": key}

    async def handle_price(self, symbol: str, tick: dict) -> None:
        with self._lock:
            fsm = self.active_runs.get(normalize_symbol(symbol))
        if not fsm:
            return
        await fsm.on_tick(tick)

    def active_symbols(self, user_id: str, account_db_id=None) -> set[str]:
        account_key = str(account_db_id or "")
        with self._lock:
            return {
                symbol
                for symbol, fsm in self.active_runs.items()
                if fsm.user_id == user_id and (not account_key or str(fsm.account.get("_id") or "") == account_key)
            }

    def active_account_ids(self, user_id: str) -> set:
        with self._lock:
            return {
                fsm.account.get("_id")
                for fsm in self.active_runs.values()
                if fsm.user_id == user_id and fsm.account.get("_id") is not None
            }

    def snapshot_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            items = [fsm.snapshot() for fsm in self.active_runs.values() if fsm.user_id == user_id]
        items.sort(key=lambda item: str(item.get("display_symbol") or item.get("symbol") or ""))
        return items

    def snapshot_all(self) -> list[dict]:
        with self._lock:
            items = [fsm.snapshot() for fsm in self.active_runs.values()]
        items.sort(key=lambda item: str(item.get("display_symbol") or item.get("symbol") or ""))
        return items


def _safe_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number):
        return None
    return number


def _coerce_tick_time(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _minute_start(value: datetime) -> datetime:
    normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.replace(second=0, microsecond=0)


trap_reversal_manager = TrapReversalManager.instance()
