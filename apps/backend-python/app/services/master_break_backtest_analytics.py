from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .master_break_levels import coerce_candle_time


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> Optional[datetime]:
    """Normalize trade timestamps to broker-face naive datetimes."""
    return coerce_candle_time(value)


def _format_period_time(value: Any) -> Optional[str]:
    """Human Date-Time for summary Max DD Period (never raw unix)."""
    dt = _parse_time(value)
    if dt is None:
        text = str(value).strip() if value is not None else ""
        return text or None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def compute_trades_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate backtest trade rows into the Master Break summary panel fields."""
    rows = list(trades or [])
    pnls = [_safe_float(trade.get("total_pnl") if trade.get("total_pnl") is not None else trade.get("pnl")) for trade in rows]
    total_pnl = round(sum(pnls), 4)
    total_trades = len(rows)
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    win_pct = round((len(wins) / total_trades) * 100.0, 2) if total_trades else 0.0
    loss_pct = round((len(losses) / total_trades) * 100.0, 2) if total_trades else 0.0
    avg_profit = round(sum(wins) / len(wins), 4) if wins else 0.0
    avg_loss = round(sum(losses) / len(losses), 4) if losses else 0.0
    max_profit = round(max(pnls), 4) if pnls else 0.0
    max_loss = round(min(pnls), 4) if pnls else 0.0

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    dd_start_idx: Optional[int] = None
    dd_end_idx: Optional[int] = None
    peak_idx = -1
    active_dd_start: Optional[int] = None

    for index, pnl in enumerate(pnls):
        equity = round(equity + pnl, 10)
        if equity >= peak:
            peak = equity
            peak_idx = index
            active_dd_start = None
            continue
        drawdown = round(peak - equity, 10)
        if active_dd_start is None:
            active_dd_start = peak_idx
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            dd_start_idx = active_dd_start
            dd_end_idx = index

    max_dd_period: dict[str, Any] = {"from": None, "to": None, "duration_trades": 0}
    if dd_start_idx is not None and dd_end_idx is not None and dd_start_idx >= 0:
        start_trade = rows[dd_start_idx]
        end_trade = rows[dd_end_idx]
        start_time = (
            start_trade.get("exit_time")
            or start_trade.get("entry_time")
            or start_trade.get("time")
            or start_trade.get("date")
        )
        end_time = (
            end_trade.get("exit_time")
            or end_trade.get("entry_time")
            or end_trade.get("time")
            or end_trade.get("date")
        )
        start_dt = _parse_time(start_time)
        end_dt = _parse_time(end_time)
        duration = None
        if start_dt and end_dt:
            duration = max(0.0, (end_dt - start_dt).total_seconds())
        max_dd_period = {
            "from": _format_period_time(start_time),
            "to": _format_period_time(end_time),
            "duration_seconds": duration,
            "duration_trades": max(0, dd_end_idx - dd_start_idx),
        }

    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "win_pct": win_pct,
        "loss_pct": loss_pct,
        "avg_profit": avg_profit,
        "avg_loss": avg_loss,
        "max_drawdown": round(max_drawdown, 4),
        "max_dd_period": max_dd_period,
        "max_profit": max_profit,
        "max_loss": max_loss,
    }
