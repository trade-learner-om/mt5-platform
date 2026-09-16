from typing import Optional


def crossed_above(price: float, level: float, prev_price: Optional[float] = None) -> bool:
    if prev_price is not None:
        return prev_price < level <= price
    return price >= level


def crossed_below(price: float, level: float, prev_price: Optional[float] = None) -> bool:
    if prev_price is not None:
        return prev_price > level >= price
    return price <= level


def structure_level(candle: dict, direction: str) -> float:
    direction = str(direction or "").upper()
    if direction == "LONG":
        return float(candle.get("high") or 0)
    return float(candle.get("low") or 0)


def crossed_structure(price: float, candle: dict, direction: str, prev_price: Optional[float] = None) -> bool:
    direction = str(direction or "").upper()
    level = structure_level(candle, direction)
    if direction == "LONG":
        return crossed_above(price, level, prev_price) or price >= level
    return crossed_below(price, level, prev_price) or price <= level


def swept_extreme(
    price: float,
    level: float,
    direction: str,
    prev_price: Optional[float] = None,
    candle_low: Optional[float] = None,
    candle_high: Optional[float] = None,
) -> bool:
    direction = str(direction or "").upper()
    if direction == "LONG":
        if crossed_below(price, level, prev_price):
            return True
        return candle_low is not None and candle_low <= level
    if crossed_above(price, level, prev_price):
        return True
    return candle_high is not None and candle_high >= level


def party_label(direction: str) -> tuple[str, str]:
    direction = str(direction or "").upper()
    if direction == "LONG":
        return "buyers", "Buyers"
    return "sellers", "Sellers"


def trap_progress_label(direction: str) -> str:
    party, _ = party_label(direction)
    return f"Early {party} in"


def trap_status_label(direction: str) -> str:
    party, _ = party_label(direction)
    return f"Early {party} trapped"


def update_swing_extreme(current: Optional[float], direction: str, price: float, candle_low: float, candle_high: float) -> float:
    direction = str(direction or "").upper()
    if direction == "LONG":
        candidates = [value for value in (current, price, candle_low) if value is not None]
        return min(candidates) if candidates else price
    candidates = [value for value in (current, price, candle_high) if value is not None]
    return max(candidates) if candidates else price
