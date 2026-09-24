"""Swing pivot detection and unmitigated structure level tracking.

Detects swing highs/lows on OHLCV frames (fractal lookback, optional ATR and
volume filters), then tracks levels forward chronologically so only unmitigated
levels remain active. Mitigation occurs when a later candle's wick breaches the
level price (strict inequality).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
COLUMN_ALIASES = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
    "tick_volume": "Volume",
    "real_volume": "Volume",
    "Open": "Open",
    "High": "High",
    "Low": "Low",
    "Close": "Close",
    "Volume": "Volume",
}

SwingKind = Literal["high", "low"]
# Fractal half-window. Callers may pass up to 50 for coarser structure.
DEFAULT_SWING_LENGTH = 5
DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_MULTIPLIER = 0.5
DEFAULT_VOLUME_SMA = 20
DEFAULT_VOLUME_SIGMA = 1.5


@dataclass(frozen=True)
class UnmitigatedLevel:
    """A swing high or low that has not yet been breached by a later candle."""

    kind: SwingKind
    price: float
    index: int
    time: Any = None
    volume: float = 0.0
    mitigated: bool = False
    mitigated_at_index: Optional[int] = None
    mitigated_at_time: Any = None

    def to_dict(self) -> dict[str, Any]:
        direction = "SHORT" if self.kind == "high" else "LONG"
        return {
            "kind": self.kind,
            "direction": direction,
            "price": float(self.price),
            "index": int(self.index),
            "time": self.time,
            "volume": float(self.volume),
            "mitigated": bool(self.mitigated),
            "mitigated_at_index": self.mitigated_at_index,
            "mitigated_at_time": self.mitigated_at_time,
        }


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))
    renamed = {}
    for col in df.columns:
        key = str(col)
        if key in COLUMN_ALIASES:
            renamed[col] = COLUMN_ALIASES[key]
        elif key.lower() in COLUMN_ALIASES:
            renamed[col] = COLUMN_ALIASES[key.lower()]
    frame = df.rename(columns=renamed).copy()
    missing = [c for c in ("Open", "High", "Low", "Close") if c not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV DataFrame missing required columns: {missing}")
    if "Volume" not in frame.columns:
        frame["Volume"] = 0.0
    for col in OHLCV_COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "time" in df.columns and "time" not in frame.columns:
        frame["time"] = df["time"].values
    elif "time" in frame.columns:
        pass
    return frame


def candles_to_ohlcv_frame(candles: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Convert chart candle dicts (lowercase keys / unix time) to an OHLCV frame."""
    if not candles:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS) + ["time"])
    rows: list[dict[str, Any]] = []
    for candle in candles:
        rows.append(
            {
                "time": candle.get("time"),
                "Open": float(candle.get("open") if candle.get("open") is not None else candle.get("Open") or 0),
                "High": float(candle.get("high") if candle.get("high") is not None else candle.get("High") or 0),
                "Low": float(candle.get("low") if candle.get("low") is not None else candle.get("Low") or 0),
                "Close": float(candle.get("close") if candle.get("close") is not None else candle.get("Close") or 0),
                "Volume": float(
                    candle.get("volume")
                    if candle.get("volume") is not None
                    else candle.get("Volume")
                    or candle.get("tick_volume")
                    or 0
                ),
            }
        )
    return pd.DataFrame(rows)


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    return np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))


def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = _true_range(high, low, close)
    n = len(tr)
    atr = np.full(n, np.nan, dtype=float)
    if n == 0 or period <= 0:
        return atr
    if n < period:
        atr[:] = float(np.nanmean(tr)) if n else np.nan
        return atr
    atr[period - 1] = float(np.mean(tr[:period]))
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    first = atr[period - 1]
    atr[: period - 1] = first
    return atr


def _adaptive_swing_length(
    atr: np.ndarray,
    *,
    base_length: int,
    min_length: int = 2,
    max_length: int = 50,
) -> int:
    """Scale fractal lookback from median ATR relative to mean ATR (clamped)."""
    valid = atr[~np.isnan(atr)]
    if len(valid) == 0 or base_length < 1:
        return max(min_length, min(max_length, base_length if base_length >= 1 else min_length))
    median_atr = float(np.median(valid))
    mean_atr = float(np.mean(valid))
    if mean_atr <= 0:
        return int(np.clip(base_length, min_length, max_length))
    scale = median_atr / mean_atr
    return int(np.clip(round(base_length * scale), min_length, max_length))


def detect_swing_pivots(
    df: pd.DataFrame,
    *,
    swing_length: int = DEFAULT_SWING_LENGTH,
    atr_adaptive: bool = False,
    use_atr_filter: bool = False,
    atr_period: int = DEFAULT_ATR_PERIOD,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    use_volume_filter: bool = False,
    volume_sma_period: int = DEFAULT_VOLUME_SMA,
    volume_sigma: float = DEFAULT_VOLUME_SIGMA,
) -> tuple[pd.Series, pd.Series]:
    """Return boolean masks for confirmed swing highs and swing lows.

    A bar at index ``i`` is a swing high when its High is strictly greater than
    the High of the ``swing_length`` bars on each side (classic fractal). Swing
    lows mirror that rule on Low.

    When ``atr_adaptive`` is True, ``swing_length`` is scaled from series ATR
    (clamped to 2..50) before fractal detection.

    When ``use_atr_filter`` is True, pivots whose own bar range
    (``High - Low``) is below ``atr_multiplier * ATR`` are dropped.

    When ``use_volume_filter`` is True, pivots must have volume at or above
    ``SMA + volume_sigma * STD`` of the volume series (falls back to SMA when
    STD is unavailable).
    """
    frame = _normalize_ohlcv_columns(df)
    n = len(frame)
    swing_high = pd.Series(False, index=frame.index)
    swing_low = pd.Series(False, index=frame.index)
    if n == 0 or swing_length < 1:
        return swing_high, swing_low

    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    volumes = frame["Volume"].to_numpy(dtype=float)
    closes = frame["Close"].to_numpy(dtype=float)

    atr = _wilder_atr(highs, lows, closes, atr_period) if (use_atr_filter or atr_adaptive) else None
    length = int(swing_length)
    if atr_adaptive and atr is not None:
        length = _adaptive_swing_length(atr, base_length=length)

    if n < (2 * length + 1) or length < 1:
        return swing_high, swing_low

    vol_sma = None
    vol_std = None
    if use_volume_filter and volume_sma_period > 0:
        vol_series = pd.Series(volumes)
        vol_sma = vol_series.rolling(volume_sma_period, min_periods=max(1, volume_sma_period // 2)).mean().to_numpy()
        vol_std = vol_series.rolling(volume_sma_period, min_periods=max(1, volume_sma_period // 2)).std(ddof=0).to_numpy()

    for i in range(length, n - length):
        left_h = highs[i - length : i]
        right_h = highs[i + 1 : i + length + 1]
        left_l = lows[i - length : i]
        right_l = lows[i + 1 : i + length + 1]

        is_high = bool(highs[i] > left_h.max() and highs[i] > right_h.max())
        is_low = bool(lows[i] < left_l.min() and lows[i] < right_l.min())

        if use_atr_filter and atr is not None and not np.isnan(atr[i]) and (is_high or is_low):
            threshold = float(atr[i]) * float(atr_multiplier)
            bar_range = float(highs[i] - lows[i])
            if bar_range < threshold:
                is_high = False
                is_low = False

        if use_volume_filter and vol_sma is not None:
            sma = vol_sma[i]
            if np.isnan(sma):
                is_high = False
                is_low = False
            else:
                threshold = float(sma)
                if vol_std is not None and not np.isnan(vol_std[i]) and volume_sigma > 0:
                    threshold = float(sma + volume_sigma * vol_std[i])
                if volumes[i] < threshold:
                    is_high = False
                    is_low = False

        if is_high:
            swing_high.iloc[i] = True
        if is_low:
            swing_low.iloc[i] = True

    return swing_high, swing_low


def calculate_unmitigated_levels(
    df: pd.DataFrame,
    *,
    swing_length: int = DEFAULT_SWING_LENGTH,
    atr_adaptive: bool = False,
    use_atr_filter: bool = False,
    atr_period: int = DEFAULT_ATR_PERIOD,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    use_volume_filter: bool = False,
    volume_sma_period: int = DEFAULT_VOLUME_SMA,
    volume_sigma: float = DEFAULT_VOLUME_SIGMA,
    mitigate_on: Literal["wick", "close"] = "wick",
    include_mitigated: bool = False,
) -> list[dict[str, Any]]:
    """Detect swing pivots and return only levels that remain unmitigated.

    Walks the series forward chronologically. Active resistance (swing highs)
    and support (swing lows) are dropped when a later bar's high/low (wick) or
    close (when ``mitigate_on="close"``) strictly breaches the level.
    """
    frame = _normalize_ohlcv_columns(df)
    if frame.empty:
        return []

    swing_high_mask, swing_low_mask = detect_swing_pivots(
        frame,
        swing_length=swing_length,
        atr_adaptive=atr_adaptive,
        use_atr_filter=use_atr_filter,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        use_volume_filter=use_volume_filter,
        volume_sma_period=volume_sma_period,
        volume_sigma=volume_sigma,
    )

    # Recompute effective length for delayed pivot registration (must match detect).
    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    closes = frame["Close"].to_numpy(dtype=float)
    volumes = frame["Volume"].to_numpy(dtype=float)
    times = frame["time"].to_numpy() if "time" in frame.columns else np.array([None] * len(frame))
    length = int(swing_length)
    if atr_adaptive:
        atr = _wilder_atr(highs, lows, closes, atr_period)
        length = _adaptive_swing_length(atr, base_length=length)

    levels: list[UnmitigatedLevel] = []
    resistance_stack: list[int] = []
    support_stack: list[int] = []

    def _breach_high(level_price: float, bar_high: float, bar_close: float) -> bool:
        if mitigate_on == "close":
            return bar_close > level_price
        return bar_high > level_price

    def _breach_low(level_price: float, bar_low: float, bar_close: float) -> bool:
        if mitigate_on == "close":
            return bar_close < level_price
        return bar_low < level_price

    n = len(frame)
    for i in range(n):
        still_res: list[int] = []
        for level_idx in resistance_stack:
            level = levels[level_idx]
            if i <= level.index:
                still_res.append(level_idx)
                continue
            if _breach_high(level.price, highs[i], closes[i]):
                levels[level_idx] = UnmitigatedLevel(
                    kind=level.kind,
                    price=level.price,
                    index=level.index,
                    time=level.time,
                    volume=level.volume,
                    mitigated=True,
                    mitigated_at_index=i,
                    mitigated_at_time=times[i] if i < len(times) else None,
                )
            else:
                still_res.append(level_idx)
        resistance_stack = still_res

        still_sup: list[int] = []
        for level_idx in support_stack:
            level = levels[level_idx]
            if i <= level.index:
                still_sup.append(level_idx)
                continue
            if _breach_low(level.price, lows[i], closes[i]):
                levels[level_idx] = UnmitigatedLevel(
                    kind=level.kind,
                    price=level.price,
                    index=level.index,
                    time=level.time,
                    volume=level.volume,
                    mitigated=True,
                    mitigated_at_index=i,
                    mitigated_at_time=times[i] if i < len(times) else None,
                )
            else:
                still_sup.append(level_idx)
        support_stack = still_sup

        # Pivots are only known once ``length`` bars have closed after the pivot.
        pivot_i = i - length
        if pivot_i >= length and pivot_i < n:
            if bool(swing_high_mask.iloc[pivot_i]):
                level = UnmitigatedLevel(
                    kind="high",
                    price=float(highs[pivot_i]),
                    index=int(pivot_i),
                    time=times[pivot_i] if pivot_i < len(times) else None,
                    volume=float(volumes[pivot_i]),
                )
                levels.append(level)
                resistance_stack.append(len(levels) - 1)
            if bool(swing_low_mask.iloc[pivot_i]):
                level = UnmitigatedLevel(
                    kind="low",
                    price=float(lows[pivot_i]),
                    index=int(pivot_i),
                    time=times[pivot_i] if pivot_i < len(times) else None,
                    volume=float(volumes[pivot_i]),
                )
                levels.append(level)
                support_stack.append(len(levels) - 1)

    active = [lvl for lvl in levels if not lvl.mitigated]
    ordered = sorted(levels if include_mitigated else active, key=lambda item: item.price, reverse=True)
    return [item.to_dict() for item in ordered]


def supports_and_resistances_from_levels(levels: Sequence[dict[str, Any]]) -> tuple[list[float], list[float]]:
    """Split unmitigated level dicts into sorted support and resistance prices."""
    supports = sorted(
        {round(float(item["price"]), 10) for item in levels if item.get("kind") == "low" and not item.get("mitigated")}
    )
    resistances = sorted(
        {round(float(item["price"]), 10) for item in levels if item.get("kind") == "high" and not item.get("mitigated")}
    )
    return supports, resistances
