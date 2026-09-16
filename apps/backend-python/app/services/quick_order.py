"""Broker-backed inputs for the live Quick Order ticket."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .metaapi_client import metaapi_service
from .risk import digits_from_symbol_spec, normalize_price_to_symbol

QUICK_ORDER_TIMEFRAMES = {"M1", "M3", "M5"}


def normalize_quick_order_timeframe(value: str) -> str:
    normalized = str(value or "").strip().upper()
    aliases = {"1M": "M1", "M1": "M1", "3M": "M3", "M3": "M3", "5M": "M5", "M5": "M5"}
    timeframe = aliases.get(normalized)
    if timeframe not in QUICK_ORDER_TIMEFRAMES:
        raise ValueError("Timeframe must be 1m, 3m, or 5m.")
    return timeframe


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _aggregate_last_completed_m3(candles: list[dict]) -> dict:
    if len(candles) < 2:
        raise ValueError("No M1 candles are available for this symbol.")
    normalized = sorted(candles, key=lambda candle: _as_datetime(candle["time"]))
    current_bucket_start = int(_as_datetime(normalized[-1]["time"]).timestamp()) // 180 * 180
    completed_bucket_starts = sorted({
        int(_as_datetime(candle["time"]).timestamp()) // 180 * 180
        for candle in normalized
        if int(_as_datetime(candle["time"]).timestamp()) // 180 * 180 < current_bucket_start
    })
    if not completed_bucket_starts:
        raise ValueError("No completed 3-minute candle is available for this symbol.")
    bucket_start = completed_bucket_starts[-1]
    bucket = [
        candle
        for candle in normalized
        if int(_as_datetime(candle["time"]).timestamp()) // 180 * 180 == bucket_start
    ]
    if not bucket:
        raise ValueError("No completed 3-minute candle is available for this symbol.")
    return {
        "time": bucket[0]["time"],
        "open": float(bucket[0]["open"]),
        "high": max(float(candle["high"]) for candle in bucket),
        "low": min(float(candle["low"]) for candle in bucket),
        "close": float(bucket[-1]["close"]),
    }


async def build_quick_order_quote(account: dict, symbol: str, timeframe: str, side: str) -> dict:
    """Return a completed-candle stop and executable quote from the selected MT5 feed."""
    normalized_timeframe = normalize_quick_order_timeframe(timeframe)
    normalized_side = str(side or "").upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Direction must be BUY or SELL.")

    token = account["api_token"]
    account_id = account["account_id"]
    if normalized_timeframe == "M3":
        candles = await metaapi_service.get_historical_candles(token, account_id, symbol, "M1", limit=8)
        candle = _aggregate_last_completed_m3(candles)
    else:
        candles = await metaapi_service.get_historical_candles(token, account_id, symbol, normalized_timeframe, limit=2)
        if len(candles) < 2:
            raise ValueError(f"No completed {normalized_timeframe} candle is available for this symbol.")
        candle = candles[-2]

    symbol_spec = await metaapi_service.get_symbol_specification(token, account_id, symbol)
    tick_size = float(symbol_spec.get("tickSize") or symbol_spec.get("point") or 0.0)
    if tick_size <= 0:
        raise ValueError("Symbol tick size is unavailable.")
    price = await metaapi_service.get_symbol_price(token, account_id, symbol)
    entry = price.get("ask") if normalized_side == "BUY" else price.get("bid")
    if entry is None:
        raise ValueError("Current market price is unavailable for this symbol.")

    candle_high = float(candle["high"])
    candle_low = float(candle["low"])
    stop_loss = candle_low - tick_size if normalized_side == "BUY" else candle_high + tick_size
    return {
        "symbol": symbol,
        "timeframe": normalized_timeframe,
        "side": normalized_side,
        "entry": normalize_price_to_symbol(float(entry), symbol_spec),
        "stop_loss": normalize_price_to_symbol(stop_loss, symbol_spec),
        "candle_high": normalize_price_to_symbol(candle_high, symbol_spec),
        "candle_low": normalize_price_to_symbol(candle_low, symbol_spec),
        "candle_time": _as_datetime(candle["time"]),
        "tick_size": tick_size,
        "price_digits": digits_from_symbol_spec(symbol_spec),
    }
