from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .master_break_levels import (
    CandleLike,
    is_green,
    is_red,
    long_entry_sl,
    master_high,
    master_low,
    short_entry_sl,
)
from .master_break_settings import MasterBreakSettings, MasterBreakTarget


class SideState(str, Enum):
    SEEKING_MASTER = "SEEKING_MASTER"
    WAIT_BREAK = "WAIT_BREAK"
    WAIT_SIGNAL = "WAIT_SIGNAL"
    PENDING = "PENDING"
    OPEN = "OPEN"


@dataclass
class MasterBreakEvent:
    type: str
    side: str
    payload: dict[str, Any] = field(default_factory=dict)


def allocate_target_quantities(
    total_qty: float,
    targets: list[MasterBreakTarget],
    *,
    volume_step: float = 0.01,
) -> list[float]:
    """Distribute total quantity across targets by qty_pct; last leg gets remainder."""
    step = float(volume_step or 0.01)
    if step <= 0:
        step = 0.01
    total = float(total_qty or 0.0)
    if total <= 0 or not targets:
        return [0.0 for _ in targets]

    allocations: list[float] = []
    assigned = 0.0
    for index, target in enumerate(targets):
        if index == len(targets) - 1:
            remaining = max(0.0, round(total - assigned, 10))
            allocations.append(remaining)
            break
        raw = total * (float(target.qty_pct) / 100.0)
        lots = (int(raw / step)) * step
        allocations.append(round(lots, 10))
        assigned += lots
    return allocations


@dataclass
class MasterBreakSideFSM:
    """Pure-ish per-side FSM. Returns events; no broker I/O."""

    side: str  # SHORT | LONG
    settings: MasterBreakSettings
    point: float = 0.01
    state: SideState = SideState.SEEKING_MASTER
    level: Optional[float] = None  # latest completed master high (short) or low (long)
    signal_extreme: Optional[float] = None  # RC.high (short) or GC.low (long)
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    quantity: float = 0.0
    remaining_qty: float = 0.0
    fill_mode: str = "STOP"  # STOP | LIMIT
    pending_order_id: Optional[str] = None
    position_id: Optional[str] = None
    realized_pnl: float = 0.0
    partials: list[dict[str, Any]] = field(default_factory=list)
    targets_hit: list[bool] = field(default_factory=list)
    breakeven_armed: bool = False
    risk_distance: float = 0.0
    last_master: Optional[dict] = None
    last_error: Optional[str] = None

    def __post_init__(self) -> None:
        self.side = str(self.side or "").upper()
        if self.side not in {"SHORT", "LONG"}:
            raise ValueError("side must be SHORT or LONG")
        try:
            self.point = float(self.point) if self.point is not None else 0.01
        except (TypeError, ValueError):
            self.point = 0.01
        if self.point <= 0:
            self.point = 0.01
        if not self.targets_hit:
            self.targets_hit = [False for _ in self.settings.targets]

    def snapshot(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "state": self.state.value,
            "level": self.level,
            "signal_extreme": self.signal_extreme,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "quantity": self.quantity,
            "remaining_qty": self.remaining_qty,
            "fill_mode": self.fill_mode,
            "pending_order_id": self.pending_order_id,
            "position_id": self.position_id,
            "realized_pnl": self.realized_pnl,
            "partials": list(self.partials),
            "targets_hit": list(self.targets_hit),
            "breakeven_armed": self.breakeven_armed,
            "risk_distance": self.risk_distance,
            "last_error": self.last_error,
        }

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        raw = dict(data or {})
        state = raw.get("state")
        if state:
            self.state = SideState(str(state))
        self.level = raw.get("level")
        self.signal_extreme = raw.get("signal_extreme")
        self.entry = raw.get("entry")
        self.stop_loss = raw.get("stop_loss")
        self.quantity = float(raw.get("quantity") or 0.0)
        self.remaining_qty = float(raw.get("remaining_qty") or 0.0)
        self.fill_mode = str(raw.get("fill_mode") or "STOP")
        self.pending_order_id = raw.get("pending_order_id")
        self.position_id = raw.get("position_id")
        self.realized_pnl = float(raw.get("realized_pnl") or 0.0)
        self.partials = list(raw.get("partials") or [])
        self.targets_hit = list(raw.get("targets_hit") or [False for _ in self.settings.targets])
        self.breakeven_armed = bool(raw.get("breakeven_armed"))
        self.risk_distance = float(raw.get("risk_distance") or 0.0)
        self.last_error = raw.get("last_error")

    def reset_to_seeking(self) -> None:
        self.state = SideState.SEEKING_MASTER
        self.level = None
        self.signal_extreme = None
        self.entry = None
        self.stop_loss = None
        self.quantity = 0.0
        self.remaining_qty = 0.0
        self.fill_mode = "STOP"
        self.pending_order_id = None
        self.position_id = None
        self.partials = []
        self.targets_hit = [False for _ in self.settings.targets]
        self.breakeven_armed = False
        self.risk_distance = 0.0

    def process_master_close(self, candle: CandleLike, previous: Optional[CandleLike] = None) -> list[MasterBreakEvent]:
        """Mark level from the latest completed master only. `previous` is unused."""
        _ = previous
        events: list[MasterBreakEvent] = []
        if self.state not in {SideState.SEEKING_MASTER, SideState.WAIT_BREAK}:
            return events

        # Any completed master sets / replaces the break level for this side.
        if self.side == "SHORT":
            level = master_high(candle)
            self.level = level
            self.last_master = dict(candle)
            self.state = SideState.WAIT_BREAK
            events.append(MasterBreakEvent("MASTER_LEVEL", self.side, {"level": level, "kind": "MASTER_HIGH"}))
        else:
            level = master_low(candle)
            self.level = level
            self.last_master = dict(candle)
            self.state = SideState.WAIT_BREAK
            events.append(MasterBreakEvent("MASTER_LEVEL", self.side, {"level": level, "kind": "MASTER_LOW"}))
        return events

    def process_exec_close(self, candle: CandleLike, *, price_for_limit_check: Optional[float] = None) -> list[MasterBreakEvent]:
        events: list[MasterBreakEvent] = []
        close = float(candle.get("close") or 0.0)

        if self.state == SideState.WAIT_BREAK and self.level is not None:
            if self.side == "SHORT" and close > float(self.level):
                self.state = SideState.WAIT_SIGNAL
                events.append(MasterBreakEvent("BREAK_CONFIRMED", self.side, {"level": self.level, "close": close}))
            elif self.side == "LONG" and close < float(self.level):
                self.state = SideState.WAIT_SIGNAL
                events.append(MasterBreakEvent("BREAK_CONFIRMED", self.side, {"level": self.level, "close": close}))
            return events

        if self.state == SideState.WAIT_SIGNAL:
            if self.side == "SHORT" and is_red(candle):
                entry, stop_loss = short_entry_sl(candle, self.point)
                self.entry = entry
                self.stop_loss = stop_loss
                self.signal_extreme = float(candle.get("high") or 0.0)
                self.risk_distance = abs(entry - stop_loss)
                ref = close if price_for_limit_check is None else float(price_for_limit_check)
                self.fill_mode = "LIMIT" if ref <= entry else "STOP"
                self.state = SideState.PENDING
                events.append(
                    MasterBreakEvent(
                        "ARM_PENDING",
                        self.side,
                        {
                            "entry": entry,
                            "stop_loss": stop_loss,
                            "signal_extreme": self.signal_extreme,
                            "fill_mode": self.fill_mode,
                            "candle": dict(candle),
                        },
                    )
                )
            elif self.side == "LONG" and is_green(candle):
                entry, stop_loss = long_entry_sl(candle, self.point)
                self.entry = entry
                self.stop_loss = stop_loss
                self.signal_extreme = float(candle.get("low") or 0.0)
                self.risk_distance = abs(entry - stop_loss)
                ref = close if price_for_limit_check is None else float(price_for_limit_check)
                self.fill_mode = "LIMIT" if ref >= entry else "STOP"
                self.state = SideState.PENDING
                events.append(
                    MasterBreakEvent(
                        "ARM_PENDING",
                        self.side,
                        {
                            "entry": entry,
                            "stop_loss": stop_loss,
                            "signal_extreme": self.signal_extreme,
                            "fill_mode": self.fill_mode,
                            "candle": dict(candle),
                        },
                    )
                )
            return events

        if self.state == SideState.PENDING and self.signal_extreme is not None:
            if self.side == "SHORT" and close > float(self.signal_extreme):
                order_id = self.pending_order_id
                self.entry = None
                self.stop_loss = None
                self.signal_extreme = None
                self.pending_order_id = None
                self.fill_mode = "STOP"
                self.state = SideState.WAIT_SIGNAL
                events.append(MasterBreakEvent("INVALIDATE_PENDING", self.side, {"order_id": order_id, "close": close}))
            elif self.side == "LONG" and close < float(self.signal_extreme):
                order_id = self.pending_order_id
                self.entry = None
                self.stop_loss = None
                self.signal_extreme = None
                self.pending_order_id = None
                self.fill_mode = "STOP"
                self.state = SideState.WAIT_SIGNAL
                events.append(MasterBreakEvent("INVALIDATE_PENDING", self.side, {"order_id": order_id, "close": close}))
        return events

    def mark_pending_placed(self, order_id: str, quantity: float, *, fill_mode: Optional[str] = None) -> None:
        self.pending_order_id = str(order_id)
        self.quantity = float(quantity)
        self.remaining_qty = float(quantity)
        if fill_mode:
            self.fill_mode = str(fill_mode)

    def process_tick(
        self,
        bid: float,
        ask: Optional[float] = None,
        *,
        high: Optional[float] = None,
        low: Optional[float] = None,
    ) -> list[MasterBreakEvent]:
        """Handle fills / partials / BE using live prices (and optional bar extremes)."""
        events: list[MasterBreakEvent] = []
        price = float(bid)
        ask_price = float(ask) if ask is not None else price
        bar_high = float(high) if high is not None else max(price, ask_price)
        bar_low = float(low) if low is not None else min(price, ask_price)

        if self.state == SideState.PENDING and self.entry is not None:
            filled = False
            if self.side == "SHORT":
                if self.fill_mode == "STOP" and bar_low <= float(self.entry):
                    filled = True
                elif self.fill_mode == "LIMIT" and bar_high >= float(self.entry):
                    filled = True
            else:
                if self.fill_mode == "STOP" and bar_high >= float(self.entry):
                    filled = True
                elif self.fill_mode == "LIMIT" and bar_low <= float(self.entry):
                    filled = True
            if filled:
                self.state = SideState.OPEN
                self.pending_order_id = None
                self.remaining_qty = float(self.quantity)
                self.targets_hit = [False for _ in self.settings.targets]
                self.breakeven_armed = False
                events.append(
                    MasterBreakEvent(
                        "FILLED",
                        self.side,
                        {"entry": self.entry, "stop_loss": self.stop_loss, "quantity": self.quantity, "fill_mode": self.fill_mode},
                    )
                )

        if self.state != SideState.OPEN or self.entry is None or self.stop_loss is None:
            return events

        risk = float(self.risk_distance) or abs(float(self.entry) - float(self.stop_loss))
        if risk <= 0:
            return events

        # Stop hit (no retry): return to seeking master.
        if self.side == "SHORT" and bar_high >= float(self.stop_loss):
            exit_price = float(self.stop_loss)
            qty = float(self.remaining_qty)
            pnl = self._pnl(exit_price, qty)
            self.realized_pnl += pnl
            events.append(
                MasterBreakEvent(
                    "STOPPED_OUT",
                    self.side,
                    {
                        "exit": exit_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "retry": False,
                        "entry": float(self.entry),
                        "stop_loss": exit_price,
                    },
                )
            )
            self.reset_to_seeking()
            return events
        if self.side == "LONG" and bar_low <= float(self.stop_loss):
            exit_price = float(self.stop_loss)
            qty = float(self.remaining_qty)
            pnl = self._pnl(exit_price, qty)
            self.realized_pnl += pnl
            events.append(
                MasterBreakEvent(
                    "STOPPED_OUT",
                    self.side,
                    {
                        "exit": exit_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "retry": False,
                        "entry": float(self.entry),
                        "stop_loss": exit_price,
                    },
                )
            )
            self.reset_to_seeking()
            return events

        # Breakeven move.
        be_r = float(self.settings.breakeven_r or 0.0)
        if be_r > 0 and not self.breakeven_armed:
            if self.side == "SHORT":
                be_price = float(self.entry) - be_r * risk
                if bar_low <= be_price:
                    self.stop_loss = float(self.entry)
                    self.breakeven_armed = True
                    events.append(MasterBreakEvent("MOVE_BREAKEVEN", self.side, {"stop_loss": self.stop_loss, "r": be_r}))
            else:
                be_price = float(self.entry) + be_r * risk
                if bar_high >= be_price:
                    self.stop_loss = float(self.entry)
                    self.breakeven_armed = True
                    events.append(MasterBreakEvent("MOVE_BREAKEVEN", self.side, {"stop_loss": self.stop_loss, "r": be_r}))

        # Target partials.
        allocations = allocate_target_quantities(self.quantity, self.settings.targets)
        for index, target in enumerate(self.settings.targets):
            if index < len(self.targets_hit) and self.targets_hit[index]:
                continue
            if self.remaining_qty <= 0:
                break
            target_price = (
                float(self.entry) - float(target.r) * risk
                if self.side == "SHORT"
                else float(self.entry) + float(target.r) * risk
            )
            hit = bar_low <= target_price if self.side == "SHORT" else bar_high >= target_price
            if not hit:
                continue
            close_qty = min(float(allocations[index] if index < len(allocations) else 0.0), float(self.remaining_qty))
            if close_qty <= 0 and index == len(self.settings.targets) - 1:
                close_qty = float(self.remaining_qty)
            if close_qty <= 0:
                self.targets_hit[index] = True
                continue
            pnl = self._pnl(target_price, close_qty)
            self.realized_pnl += pnl
            self.remaining_qty = round(max(0.0, self.remaining_qty - close_qty), 10)
            self.targets_hit[index] = True
            partial = {"r": float(target.r), "price": target_price, "qty": close_qty, "pnl": pnl}
            self.partials.append(partial)
            events.append(MasterBreakEvent("PARTIAL_EXIT", self.side, partial))

        if self.remaining_qty <= 1e-12:
            events.append(
                MasterBreakEvent(
                    "TRADE_CLOSED",
                    self.side,
                    {"realized_pnl": self.realized_pnl, "partials": list(self.partials)},
                )
            )
            self.reset_to_seeking()
        return events

    def _pnl(self, exit_price: float, qty: float) -> float:
        """Price-distance PnL proxy (contract sizing applied by caller/runtime if needed)."""
        if self.entry is None:
            return 0.0
        if self.side == "SHORT":
            return (float(self.entry) - float(exit_price)) * float(qty)
        return (float(exit_price) - float(self.entry)) * float(qty)
