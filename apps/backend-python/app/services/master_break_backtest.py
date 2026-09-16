from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .master_break_backtest_analytics import compute_trades_summary
from .master_break_fsm import MasterBreakSideFSM, SideState
from .master_break_levels import (
    CandleLike,
    as_float,
    coerce_candle_time,
    completed_master_bars,
    is_green,
    is_red,
    master_timeframe_seconds,
)
from .master_break_risk import pnl_from_fill, quantity_from_risk
from .master_break_settings import MasterBreakSettings

_BROKER_FACE_MIN = datetime.min


def _is_gold_symbol(symbol: str) -> bool:
    upper = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
    return "XAU" in upper or upper == "GOLD" or upper.startswith("GOLD")


def _candle_time_key(candle: CandleLike) -> datetime:
    return coerce_candle_time(candle.get("time")) or _BROKER_FACE_MIN


def _master_close_time(master: CandleLike, master_seconds: int) -> datetime:
    """Master candle `time` is bucket open; level is tradable only after close."""
    return _candle_time_key(master) + timedelta(seconds=int(master_seconds))


def _iso_time(value: Any) -> Optional[str]:
    """Broker-face ISO without timezone offset (no geographic UTC implication)."""
    if value is None:
        return None
    dt = coerce_candle_time(value)
    if dt is None:
        text = str(value).strip()
        return text or None
    return dt.isoformat(sep="T", timespec="seconds")


def _candle_color(candle: CandleLike) -> str:
    if is_green(candle):
        return "green"
    if is_red(candle):
        return "red"
    return "doji"


def _empty_side_slot() -> dict[str, Any]:
    return {
        "level": None,
        "level_kind": None,
        "exec_closed_beyond": "no",
        "exec_close_time": None,
        "exec_close": None,
        "exec_high": None,
        "exec_low": None,
        "side_breached": None,
        "bias_formed": None,
        "signal_candle_color": None,
        "signal_high": None,
        "signal_low": None,
        "planned_entry": None,
        "planned_sl": None,
        "quantity": None,
        "entry_filled": "no",
        "entry_fill_time": None,
        "exit_time": None,
        "result_pnl": None,
    }


def _make_master_row(master: CandleLike, master_timeframe: str) -> dict[str, Any]:
    open_, high, low, close = (
        as_float(master.get("open")),
        as_float(master.get("high")),
        as_float(master.get("low")),
        as_float(master.get("close")),
    )
    return {
        "time": _iso_time(master.get("time")),
        "master_timeframe": master_timeframe,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "color": _candle_color(master),
        "sides": {
            "SHORT": _empty_side_slot(),
            "LONG": _empty_side_slot(),
        },
    }


def _in_range(when: Any, range_start: Optional[datetime], range_end: Optional[datetime]) -> bool:
    if range_start is None and range_end is None:
        return True
    dt = coerce_candle_time(when)
    if dt is None:
        return False
    if range_start is not None:
        start = coerce_candle_time(range_start)
        if start is not None and dt < start:
            return False
    if range_end is not None:
        end = coerce_candle_time(range_end)
        if end is not None and dt > end:
            return False
    return True


def simulate_master_break_backtest(
    symbol_spec: dict[str, Any],
    master_candles: list[dict[str, Any]],
    exec_candles: list[dict[str, Any]],
    settings: MasterBreakSettings | dict[str, Any],
    point: float,
    *,
    range_start: Optional[datetime] = None,
    range_end: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Dual-side bar simulation for Master Break.

    Also emits `master_rows`: one audit row per completed master candle in range
    (no in-range master bars skipped).
    """
    cfg = settings if isinstance(settings, MasterBreakSettings) else MasterBreakSettings.from_mapping(settings)
    symbol = str(symbol_spec.get("symbol") or "XAUUSD")
    if not _is_gold_symbol(symbol):
        raise ValueError("Master Break backtest supports XAUUSD/GOLD only")

    point_size = as_float(point, 0.01)
    if point_size <= 0:
        point_size = 0.01

    masters = completed_master_bars(master_candles, timeframe=cfg.master_timeframe, drop_in_progress=True)
    execs = sorted(list(exec_candles or []), key=_candle_time_key)
    if len(execs) > 1:
        execs = execs[:-1]

    master_seconds = master_timeframe_seconds(cfg.master_timeframe)

    short_fsm = MasterBreakSideFSM(side="SHORT", settings=cfg, point=point_size)
    long_fsm = MasterBreakSideFSM(side="LONG", settings=cfg, point=point_size)

    trades: list[dict[str, Any]] = []
    rolls: list[dict[str, Any]] = []
    open_trades: dict[str, dict[str, Any]] = {}

    # All master rows by time key; filtered list returned for in-range only.
    master_rows_by_key: dict[str, dict[str, Any]] = {}
    master_row_order: list[str] = []
    # Which master row currently owns the active level / pending / open for each side.
    side_owner_key: dict[str, Optional[str]] = {"SHORT": None, "LONG": None}
    # Do not fill on the same exec bar that armed the pending stop.
    armed_bar_time: dict[str, Optional[datetime]] = {"SHORT": None, "LONG": None}

    master_index = 0
    previous_master: Optional[dict] = None

    def _valued_pnl(side: str, entry: float, exit_price: float, qty: float) -> float:
        return pnl_from_fill(
            side,
            entry,
            exit_price,
            qty,
            symbol_spec=symbol_spec,
            symbol=symbol,
        )

    def _append_roll(event_type: str, side: str, when: Any, **payload: Any) -> None:
        rolls.append({"event": event_type, "side": side, "time": when, **payload})

    def _row_key(master: CandleLike) -> str:
        return _iso_time(master.get("time")) or str(id(master))

    def _ensure_master_row(master: CandleLike) -> Optional[dict[str, Any]]:
        key = _row_key(master)
        if key not in master_rows_by_key:
            master_rows_by_key[key] = _make_master_row(master, cfg.master_timeframe)
            master_row_order.append(key)
        if not _in_range(master.get("time"), range_start, range_end):
            return None
        return master_rows_by_key[key]

    def _side_slot(owner_key: Optional[str], side: str) -> Optional[dict[str, Any]]:
        if not owner_key:
            return None
        row = master_rows_by_key.get(owner_key)
        if not row:
            return None
        return row["sides"][side]

    def _trade_entry(trade: dict[str, Any]) -> float:
        """Entry price from open trade snapshot (never float(None))."""
        return as_float(trade.get("entry"), as_float(trade.get("planned_entry")))

    def _close_open_trade(side: str, exit_price: float, exit_time: Any, reason: str) -> None:
        trade = open_trades.pop(side, None)
        if not trade:
            return
        exit_iso = _iso_time(exit_time)
        qty = as_float(trade.get("remaining_qty"))
        entry = _trade_entry(trade)
        if qty > 0 and entry:
            pnl = _valued_pnl(side, entry, exit_price, qty)
            trade["partials"].append({"type": reason, "price": exit_price, "qty": qty, "pnl": pnl, "time": exit_iso})
            trade["total_pnl"] = round(as_float(trade.get("total_pnl")) + pnl, 6)
            trade["remaining_qty"] = 0.0
        elif qty > 0:
            trade["remaining_qty"] = 0.0
        trade["final_exit"] = exit_price
        trade["exit_time"] = exit_iso
        trade["exit_reason"] = reason
        trades.append(trade)
        _append_roll(reason, side, exit_iso or exit_time, exit=exit_price, pnl=trade.get("total_pnl"))
        slot = _side_slot(trade.get("master_row_key") or side_owner_key.get(side), side)
        if slot and slot.get("entry_filled") == "yes":
            slot["exit_time"] = exit_iso
            slot["result_pnl"] = trade.get("total_pnl")

    def _advance_master(master: dict) -> None:
        nonlocal previous_master
        # Always register the candle so in-range filtering can include every bar.
        _ensure_master_row(master)
        key = _row_key(master)
        for fsm in (short_fsm, long_fsm):
            for event in fsm.process_master_close(master, previous_master):
                _append_roll(event.type, event.side, master.get("time"), **event.payload)
                if event.type == "MASTER_LEVEL":
                    side_owner_key[fsm.side] = key
                    slot = _side_slot(key, fsm.side)
                    if slot is not None:
                        slot["level"] = event.payload.get("level")
                        slot["level_kind"] = event.payload.get("kind")
        previous_master = master

    def _handle_side_events(fsm: MasterBreakSideFSM, exec_bar: dict, events: list) -> None:
        bar_time = exec_bar.get("time")
        for event in events:
            _append_roll(event.type, event.side, bar_time, **event.payload)
            owner = side_owner_key.get(fsm.side)
            slot = _side_slot(owner, fsm.side)

            if event.type == "BREAK_CONFIRMED" and slot is not None:
                slot["exec_closed_beyond"] = "yes"
                slot["exec_close_time"] = _iso_time(bar_time)
                slot["exec_close"] = as_float(event.payload.get("close"), as_float(exec_bar.get("close")))
                slot["exec_high"] = as_float(exec_bar.get("high"))
                slot["exec_low"] = as_float(exec_bar.get("low"))
                slot["side_breached"] = "High" if fsm.side == "SHORT" else "Low"
                slot["bias_formed"] = "Short" if fsm.side == "SHORT" else "Long"

            elif event.type == "ARM_PENDING":
                entry = as_float(event.payload.get("entry"))
                stop_loss = as_float(event.payload.get("stop_loss"))
                qty = quantity_from_risk(
                    cfg.risk_amount,
                    entry,
                    stop_loss,
                    symbol_spec=symbol_spec,
                    symbol=symbol,
                )
                if qty <= 0:
                    fsm.state = SideState.WAIT_SIGNAL
                    fsm.entry = None
                    fsm.stop_loss = None
                    fsm.signal_extreme = None
                    continue
                # Sell/buy stop pending: always STOP fill semantics in backtest.
                fsm.mark_pending_placed(f"bt-{fsm.side}-{len(rolls)}", qty, fill_mode="STOP")
                armed_bar_time[fsm.side] = _candle_time_key(exec_bar)
                signal = event.payload.get("candle") or exec_bar
                if slot is not None:
                    slot["signal_candle_color"] = _candle_color(signal)
                    slot["signal_high"] = as_float(signal.get("high"))
                    slot["signal_low"] = as_float(signal.get("low"))
                    slot["planned_entry"] = entry
                    slot["planned_sl"] = stop_loss
                    slot["quantity"] = qty
                    if not slot.get("bias_formed"):
                        slot["bias_formed"] = "Short" if fsm.side == "SHORT" else "Long"
                        slot["side_breached"] = "High" if fsm.side == "SHORT" else "Low"

            elif event.type == "FILLED":
                armed_bar_time[fsm.side] = None
                entry_iso = _iso_time(bar_time)
                # Prefer event payload: same-bar FILL+SL resets fsm.entry before handlers run.
                entry = as_float(event.payload.get("entry"), as_float(fsm.entry))
                stop_loss = as_float(event.payload.get("stop_loss"), as_float(fsm.stop_loss))
                quantity = as_float(event.payload.get("quantity"), as_float(fsm.quantity))
                remaining = as_float(fsm.remaining_qty, quantity)
                if remaining <= 0:
                    remaining = quantity
                planned = as_float(slot.get("planned_entry")) if slot else 0.0
                if not entry and planned:
                    entry = planned
                open_trades[fsm.side] = {
                    "direction": fsm.side,
                    "side": fsm.side,
                    "entry": entry,
                    "stop_loss": stop_loss,
                    "quantity": quantity,
                    "remaining_qty": remaining,
                    "entry_time": entry_iso,
                    "date": str(entry_iso)[:10] if entry_iso else None,
                    "time": entry_iso,
                    "partials": [],
                    "total_pnl": 0.0,
                    "final_exit": None,
                    "exit_time": None,
                    "fill_mode": event.payload.get("fill_mode") or fsm.fill_mode,
                    "master_row_key": owner,
                    "planned_entry": planned or entry,
                }
                if slot is not None:
                    slot["entry_filled"] = "yes"
                    slot["entry_fill_time"] = _iso_time(bar_time)
                    slot["quantity"] = quantity
                    slot["result_pnl"] = None

            elif event.type == "INVALIDATE_PENDING" and slot is not None:
                armed_bar_time[fsm.side] = None
                # Keep planned levels; mark unfilled.
                slot["entry_filled"] = "no"
                slot["entry_fill_time"] = None
                slot["exit_time"] = None
                slot["result_pnl"] = None

            elif event.type == "MOVE_BREAKEVEN":
                trade = open_trades.get(fsm.side)
                if trade:
                    trade["stop_loss"] = as_float(event.payload.get("stop_loss"), as_float(trade.get("stop_loss")))
                    trade["breakeven"] = True

            elif event.type == "PARTIAL_EXIT":
                trade = open_trades.get(fsm.side)
                if not trade:
                    continue
                entry = _trade_entry(trade)
                price = as_float(event.payload.get("price"))
                qty = as_float(event.payload.get("qty"))
                pnl = _valued_pnl(fsm.side, entry, price, qty) if entry and qty else 0.0
                partial = {
                    "type": "PARTIAL",
                    "r": event.payload.get("r"),
                    "price": price,
                    "qty": qty,
                    "pnl": pnl,
                    "time": bar_time,
                }
                trade["partials"].append(partial)
                trade["total_pnl"] = round(as_float(trade.get("total_pnl")) + as_float(partial["pnl"]), 6)
                trade["remaining_qty"] = as_float(fsm.remaining_qty, as_float(trade.get("remaining_qty")) - qty)
                slot = _side_slot(trade.get("master_row_key"), fsm.side)
                if slot is not None:
                    slot["result_pnl"] = trade["total_pnl"]

            elif event.type == "STOPPED_OUT":
                trade = open_trades.get(fsm.side)
                if not trade:
                    continue
                before_sl = trade.get("stop_loss")
                exit_price = as_float(event.payload.get("exit"), as_float(before_sl))
                qty = as_float(event.payload.get("quantity"), as_float(trade.get("remaining_qty")))
                entry = _trade_entry(trade) or as_float(event.payload.get("entry"))
                pnl = _valued_pnl(fsm.side, entry, exit_price, qty) if entry and qty else 0.0
                if entry and not trade.get("entry"):
                    trade["entry"] = entry
                trade["partials"].append({"type": "SL", "price": exit_price, "qty": qty, "pnl": pnl, "time": bar_time})
                trade["total_pnl"] = round(as_float(trade.get("total_pnl")) + pnl, 6)
                trade["remaining_qty"] = 0.0
                trade["final_exit"] = exit_price
                trade["exit_time"] = _iso_time(bar_time)
                trade["exit_reason"] = "SL"
                trades.append(trade)
                open_trades.pop(fsm.side, None)
                slot = _side_slot(trade.get("master_row_key"), fsm.side)
                if slot is not None:
                    slot["exit_time"] = _iso_time(bar_time)
                    slot["result_pnl"] = trade["total_pnl"]

            elif event.type == "TRADE_CLOSED":
                trade = open_trades.get(fsm.side)
                if not trade:
                    continue
                trade["final_exit"] = trade["partials"][-1]["price"] if trade["partials"] else trade.get("entry")
                trade["exit_time"] = _iso_time(bar_time)
                trade["exit_reason"] = "TARGETS"
                trade["remaining_qty"] = 0.0
                trades.append(trade)
                open_trades.pop(fsm.side, None)
                slot = _side_slot(trade.get("master_row_key"), fsm.side)
                if slot is not None:
                    slot["exit_time"] = _iso_time(bar_time)
                    slot["result_pnl"] = trade.get("total_pnl")

    for exec_bar in execs:
        bar_dt = _candle_time_key(exec_bar)

        # Activate masters only after they close (open + TF), not at open.
        while master_index < len(masters):
            master = masters[master_index]
            if _master_close_time(master, master_seconds) > bar_dt:
                break
            _advance_master(master)
            master_index += 1

        for fsm in (short_fsm, long_fsm):
            events = list(fsm.process_exec_close(exec_bar))
            # ARM_PENDING qty handling is inside _handle_side_events.
            _handle_side_events(fsm, exec_bar, events)

            if fsm.state == SideState.PENDING and fsm.entry is not None:
                # Fill only on a subsequent candle after the red/green arm bar.
                arm_time = armed_bar_time.get(fsm.side)
                if arm_time is None or bar_dt > arm_time:
                    fsm.fill_mode = "STOP"
                    high = as_float(exec_bar.get("high"))
                    low = as_float(exec_bar.get("low"))
                    tick_events = list(fsm.process_tick(as_float(exec_bar.get("close")), high=high, low=low))
                    _handle_side_events(fsm, exec_bar, tick_events)

            if fsm.state == SideState.OPEN and fsm.side in open_trades:
                high = as_float(exec_bar.get("high"))
                low = as_float(exec_bar.get("low"))
                tick_events = list(fsm.process_tick(as_float(exec_bar.get("close")), high=high, low=low))
                _handle_side_events(fsm, exec_bar, tick_events)

    # Drain remaining masters after last exec (still no skips for in-range bars).
    while master_index < len(masters):
        _advance_master(masters[master_index])
        master_index += 1

    if execs:
        last = execs[-1]
        last_close = as_float(last.get("close"))
        for side in list(open_trades.keys()):
            _close_open_trade(side, last_close, last.get("time"), "RANGE_END")

    master_rows = [
        master_rows_by_key[key]
        for key in master_row_order
        if _in_range(master_rows_by_key[key].get("time"), range_start, range_end)
    ]

    summary_inputs = compute_trades_summary(trades)
    return {
        "trades": trades,
        "rolls": rolls,
        "master_rows": master_rows,
        "summary": summary_inputs,
        "summary_inputs": summary_inputs,
        "settings": cfg.to_dict(),
        "symbol": symbol,
    }
