"""Pure helpers for Scheduled Break Trade direction, sizing limits, and entry/SL."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .risk import is_gold_symbol, pip_size_for_symbol

CandleLike = Mapping[str, Any]

SUPPORTED_TIMEFRAMES = frozenset({"M1", "M5", "M15"})

PRIMARY_STATUSES = (
    "INITIATED",
    "ARMED",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "TARGET_EXIT",
    "STOP_EXIT",
    "USER_EXIT",
    "CANCELLED",
)
RETRY_STATUSES = (
    "RETRY_INITIATED",
    "RETRY_ARMED",
    "RETRY_ORDER_PLACED",
    "RETRY_ORDER_FILLED",
    "RETRY_TARGET_EXIT",
    "RETRY_STOP_EXIT",
    "RETRY_USER_EXIT",
    "RETRY_CANCELLED",
)
ALL_STATUSES = PRIMARY_STATUSES + RETRY_STATUSES

WATCHING_STATUSES = frozenset({"INITIATED", "ARMED", "RETRY_INITIATED", "RETRY_ARMED"})
ORDER_TRACKING_STATUSES = frozenset(
    {
        "ORDER_PLACED",
        "ORDER_FILLED",
        "RETRY_ORDER_PLACED",
        "RETRY_ORDER_FILLED",
    }
)
ACTIVE_STATUSES = WATCHING_STATUSES | ORDER_TRACKING_STATUSES
CANCELLABLE_STATUSES = frozenset(
    {
        "INITIATED",
        "ARMED",
        "ORDER_PLACED",
        "RETRY_INITIATED",
        "RETRY_ARMED",
        "RETRY_ORDER_PLACED",
    }
)
TERMINAL_STATUSES = frozenset(
    {
        "TARGET_EXIT",
        "STOP_EXIT",
        "USER_EXIT",
        "CANCELLED",
        "RETRY_TARGET_EXIT",
        "RETRY_STOP_EXIT",
        "RETRY_USER_EXIT",
        "RETRY_CANCELLED",
    }
)

PRICE_EPSILON = 1e-9
MIN_TARGET_R = 4.0


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_scheduled_timeframe(value: str) -> str:
    key = str(value or "").strip().upper()
    aliases = {"1M": "M1", "5M": "M5", "15M": "M15", "1MIN": "M1", "5MIN": "M5", "15MIN": "M15"}
    key = aliases.get(key, key)
    if key not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported scheduled trade timeframe: {value}")
    return key


def scheduled_pip_size(symbol: str) -> float:
    if is_gold_symbol(symbol):
        return 0.10
    return float(pip_size_for_symbol(symbol) or 0.0001)


def max_signal_candle_pips(symbol: str) -> float:
    if is_gold_symbol(symbol):
        return 100.0
    return 12.0


def candle_range_pips(candle: CandleLike, pip_size: float) -> float:
    pip = as_float(pip_size)
    if pip <= 0:
        return 0.0
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    return abs(high - low) / pip


def is_oversized_signal_candle(candle: CandleLike, symbol: str, pip_size: Optional[float] = None) -> bool:
    size = scheduled_pip_size(symbol) if pip_size is None else as_float(pip_size)
    return candle_range_pips(candle, size) > max_signal_candle_pips(symbol) + PRICE_EPSILON


def resolve_side_from_level(level: float, mid_price: float) -> str:
    level_f = as_float(level)
    mid_f = as_float(mid_price)
    if mid_f <= 0:
        raise ValueError("Live mid price is unavailable")
    if abs(level_f - mid_f) <= PRICE_EPSILON:
        raise ValueError("Level cannot equal the live mid price")
    if level_f > mid_f:
        return "SELL"
    return "BUY"


def is_red(candle: CandleLike) -> bool:
    return as_float(candle.get("close")) < as_float(candle.get("open")) - PRICE_EPSILON


def is_green(candle: CandleLike) -> bool:
    return as_float(candle.get("close")) > as_float(candle.get("open")) + PRICE_EPSILON


def sell_entry_sl(red_candle: CandleLike, point: float) -> tuple[float, float]:
    point_f = as_float(point)
    entry = as_float(red_candle.get("low")) - point_f
    stop_loss = as_float(red_candle.get("high")) + (3.0 * point_f)
    return entry, stop_loss


def buy_entry_sl(green_candle: CandleLike, point: float) -> tuple[float, float]:
    point_f = as_float(point)
    entry = as_float(green_candle.get("high")) + point_f
    stop_loss = as_float(green_candle.get("low")) - (3.0 * point_f)
    return entry, stop_loss


def entry_sl_for_side(side: str, candle: CandleLike, point: float) -> tuple[float, float]:
    if str(side or "").upper() == "SELL":
        return sell_entry_sl(candle, point)
    return buy_entry_sl(candle, point)


def risk_reward_multiple(side: str, entry: float, stop_loss: float, target: float) -> float:
    entry_f = as_float(entry)
    stop_f = as_float(stop_loss)
    target_f = as_float(target)
    risk = abs(entry_f - stop_f)
    if risk <= PRICE_EPSILON:
        return 0.0
    side_u = str(side or "").upper()
    if side_u == "SELL":
        reward = entry_f - target_f
    else:
        reward = target_f - entry_f
    if reward <= 0:
        return 0.0
    return reward / risk


def usable_target(side: str, entry: float, stop_loss: float, target: Optional[float]) -> Optional[float]:
    if target is None:
        return None
    try:
        target_f = float(target)
    except (TypeError, ValueError):
        return None
    if risk_reward_multiple(side, entry, stop_loss, target_f) + PRICE_EPSILON < MIN_TARGET_R:
        return None
    return target_f


def level_broken_on_close(side: str, candle: CandleLike, level: float) -> bool:
    close = as_float(candle.get("close"))
    level_f = as_float(level)
    if str(side or "").upper() == "SELL":
        return close > level_f + PRICE_EPSILON
    return close < level_f - PRICE_EPSILON
