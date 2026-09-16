def _body(candle: dict) -> float:
    return abs(float(candle["close"]) - float(candle["open"]))


def _range(candle: dict) -> float:
    return float(candle["high"]) - float(candle["low"])


def _upper_wick(candle: dict) -> float:
    return float(candle["high"]) - max(float(candle["open"]), float(candle["close"]))


def _lower_wick(candle: dict) -> float:
    return min(float(candle["open"]), float(candle["close"])) - float(candle["low"])


def _point_size(symbol_spec: dict) -> float:
    point = float(symbol_spec.get("point") or 0)
    if point > 0:
        return point
    tick_size = float(symbol_spec.get("tickSize") or 0)
    if tick_size > 0:
        return tick_size
    digits = symbol_spec.get("digits")
    if digits is not None:
        try:
            return 10 ** (-int(digits))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _is_shooting_star(candle: dict) -> bool:
    body = _body(candle)
    total_range = _range(candle)
    if body <= 0 or total_range <= 0:
        return False
    if body >= (0.2 * total_range):
        return False
    rejection_wick = _upper_wick(candle)
    opposite_wick = _lower_wick(candle)
    return rejection_wick > (0.5 * body) and opposite_wick <= (0.5 * rejection_wick)


def _is_hammer(candle: dict) -> bool:
    body = _body(candle)
    total_range = _range(candle)
    if body <= 0 or total_range <= 0:
        return False
    if body >= (0.2 * total_range):
        return False
    rejection_wick = _lower_wick(candle)
    opposite_wick = _upper_wick(candle)
    return rejection_wick > (0.5 * body) and opposite_wick <= (0.5 * rejection_wick)


def _has_min_candle_range(candle: dict, symbol_spec: dict, min_points: float = 15.0) -> bool:
    point_size = _point_size(symbol_spec)
    if point_size <= 0:
        return True
    return _range(candle) >= (float(min_points) * point_size)


def format_candle_ohlc_text(candle: dict) -> str:
    return (
        f"OHLC - {candle.get('open')} - {candle.get('high')} - {candle.get('low')} - {candle.get('close')}"
    )
