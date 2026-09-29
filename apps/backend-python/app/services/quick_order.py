"""Last completed candle inputs for the SL order desk."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .metaapi_client import metaapi_service
from .risk import calc_sl_pips, digits_from_symbol_spec, normalize_price_to_symbol

QUICK_ORDER_TIMEFRAMES = {"M1", "M5", "M15"}


def normalize_quick_order_timeframe(value: str) -> str:
    normalized = str(value or "").strip().upper()
    aliases = {
        "1M": "M1",
        "M1": "M1",
        "5M": "M5",
        "M5": "M5",
        "15M": "M15",
        "M15": "M15",
    }
    timeframe = aliases.get(normalized)
    if timeframe not in QUICK_ORDER_TIMEFRAMES:
        raise ValueError("Timeframe must be M1, M5, or M15.")
    return timeframe


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


async def build_quick_order_quote(
    account: dict,
    symbol: str,
    timeframe: str,
    side: Optional[str] = None,
) -> dict:
    """Return the last completed candle and, once a side is chosen, the SL entry and stop."""
    normalized_timeframe = normalize_quick_order_timeframe(timeframe)
    normalized_side = str(side or "").strip().upper()
    if normalized_side and normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Direction must be BUY or SELL.")

    token = account["api_token"]
    account_id = account["account_id"]
    candles = await metaapi_service.get_historical_candles(
        token, account_id, symbol, normalized_timeframe, limit=2
    )
    if len(candles) < 2:
        raise ValueError(f"No completed {normalized_timeframe} candle is available for this symbol.")
    candle = candles[-2]

    symbol_spec = await metaapi_service.get_symbol_specification(token, account_id, symbol)
    tick_size = float(symbol_spec.get("tickSize") or symbol_spec.get("point") or 0.0)
    if tick_size <= 0:
        raise ValueError("Symbol tick size is unavailable.")

    candle_open = normalize_price_to_symbol(float(candle["open"]), symbol_spec)
    candle_high = normalize_price_to_symbol(float(candle["high"]), symbol_spec)
    candle_low = normalize_price_to_symbol(float(candle["low"]), symbol_spec)
    candle_close = normalize_price_to_symbol(float(candle["close"]), symbol_spec)
    quote = {
        "symbol": symbol,
        "timeframe": normalized_timeframe,
        "side": normalized_side or None,
        "entry": None,
        "stop_loss": None,
        "sl_pips": None,
        "candle_open": candle_open,
        "candle_high": candle_high,
        "candle_low": candle_low,
        "candle_close": candle_close,
        "candle_time": _as_datetime(candle["time"]),
        "tick_size": tick_size,
        "price_digits": digits_from_symbol_spec(symbol_spec),
    }
    if normalized_side not in {"BUY", "SELL"}:
        return quote

    if normalized_side == "BUY":
        entry = candle_high + tick_size
        stop_loss = candle_low - tick_size
    else:
        entry = candle_low - tick_size
        stop_loss = candle_high + tick_size
    entry = normalize_price_to_symbol(entry, symbol_spec)
    stop_loss = normalize_price_to_symbol(stop_loss, symbol_spec)
    quote["entry"] = entry
    quote["stop_loss"] = stop_loss
    quote["sl_pips"] = calc_sl_pips(symbol, entry, stop_loss)
    return quote
