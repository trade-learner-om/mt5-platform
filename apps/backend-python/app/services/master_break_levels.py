from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

CandleLike = dict[str, Any]

_TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "H6": 21600,
    "H12": 43200,
    "D1": 86400,
}


def as_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; None/invalid → default (never raises on None)."""
    if value is None or value == "":
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(default)
        except (TypeError, ValueError):
            return 0.0


def _normalize_tf(value: str) -> str:
    raw = str(value or "").strip().upper()
    aliases = {"D": "D1", "1D": "D1", "6H": "H6", "12H": "H12", "4H": "H4"}
    return aliases.get(raw, raw)


def master_timeframe_seconds(timeframe: str) -> int:
    """Seconds in one master bar (bucket open → close)."""
    key = _normalize_tf(timeframe)
    seconds = _TIMEFRAME_SECONDS.get(key)
    if not seconds:
        raise ValueError(f"Unsupported master timeframe: {timeframe}")
    return int(seconds)


def _ohlc(candle: CandleLike) -> tuple[float, float, float, float]:
    return (
        as_float(candle.get("open")),
        as_float(candle.get("high")),
        as_float(candle.get("low")),
        as_float(candle.get("close")),
    )


def is_green(candle: CandleLike) -> bool:
    open_, _high, _low, close = _ohlc(candle)
    return close > open_


def is_red(candle: CandleLike) -> bool:
    open_, _high, _low, close = _ohlc(candle)
    return close < open_


def master_high(candle: CandleLike) -> float:
    """Short break level: high of the latest completed master candle."""
    return as_float(candle.get("high"))


def master_low(candle: CandleLike) -> float:
    """Long break level: low of the latest completed master candle."""
    return as_float(candle.get("low"))


def short_entry_sl(rc: CandleLike, point: float) -> tuple[float, float]:
    """SELL STOP entry / SL from red exec candle + one broker point."""
    point = as_float(point)
    entry = as_float(rc.get("low")) - point
    stop_loss = as_float(rc.get("high")) + point
    return entry, stop_loss


def long_entry_sl(gc: CandleLike, point: float) -> tuple[float, float]:
    """BUY STOP entry / SL from green exec candle + one broker point."""
    point = as_float(point)
    entry = as_float(gc.get("high")) + point
    stop_loss = as_float(gc.get("low")) - point
    return entry, stop_loss


def _broker_face_naive(dt: datetime) -> datetime:
    """Keep wall-clock components; drop tzinfo. Never astimezone-shift the face."""
    return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)


def _epoch_to_broker_face(ts: float) -> datetime:
    """MT5 epochs are broker-server faces; decode as UTC-labeled naive wall time."""
    if ts > 1e12:
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def coerce_candle_time(value: Any) -> Optional[datetime]:
    """Parse candle time as broker server face (naive). No geographic TZ conversion."""
    if isinstance(value, datetime):
        return _broker_face_naive(value)
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _epoch_to_broker_face(float(value))
    # numpy.int64 and similar numeric types
    try:
        if hasattr(value, "item"):
            item = value.item()
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                return _epoch_to_broker_face(float(item))
    except Exception:
        pass
    text = str(value).strip()
    # Production chart/backtest candles often stringify unix epochs ("1704067200").
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return _epoch_to_broker_face(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return _epoch_to_broker_face(float(text))
        except ValueError:
            return None
    return _broker_face_naive(parsed)


def completed_master_bars(
    candles: Sequence[CandleLike],
    *,
    now: Optional[datetime] = None,
    timeframe: Optional[str] = None,
    bar_seconds: Optional[int] = None,
    drop_in_progress: bool = True,
) -> list[CandleLike]:
    """Return completed master bars, optionally dropping the in-progress last bucket."""
    bars = [dict(candle) for candle in candles or []]
    bars.sort(key=lambda item: coerce_candle_time(item.get("time")) or datetime.min)
    if not bars or not drop_in_progress:
        return bars

    seconds = bar_seconds
    if seconds is None and timeframe:
        seconds = _TIMEFRAME_SECONDS.get(_normalize_tf(timeframe))

    last = bars[-1]
    last_time = coerce_candle_time(last.get("time"))
    if last_time is None:
        return bars[:-1]

    if now is None:
        reference = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        reference = coerce_candle_time(now) or _broker_face_naive(now)

    if seconds and seconds > 0:
        bucket_end = last_time + timedelta(seconds=int(seconds))
        if bucket_end > reference:
            return bars[:-1]
        return bars

    # Without bar length, treat the last seeded bar as forming (MT5 convention).
    return bars[:-1]
