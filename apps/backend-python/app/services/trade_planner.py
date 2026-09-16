from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException

from ..config import settings
from .metaapi_client import metaapi_service
from .risk import calc_quantity, calc_rr, calc_sl_pips, infer_point_size, pip_size_for_symbol


def trade_plan_direction(strong_swing_type: str) -> str:
    normalized = str(strong_swing_type or "").upper().strip()
    if normalized == "STRONG_HIGH":
        return "SHORT"
    if normalized == "STRONG_LOW":
        return "LONG"
    raise HTTPException(status_code=400, detail="strong_swing_type must be STRONG_LOW or STRONG_HIGH")


def normalize_float_list(values: Optional[List[float]], field_name: str) -> List[float]:
    normalized: List[float] = []
    for raw in values or []:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{field_name} must contain valid numbers")
        if value <= 0:
            raise HTTPException(status_code=400, detail=f"{field_name} must contain positive numbers")
        normalized.append(value)
    return normalized


def normalize_trade_plan_allocations(
    target_count: int,
    values: Optional[List[Optional[float]]],
    breakeven_at_t1: bool = False,
) -> List[float]:
    if target_count <= 0:
        return []
    if target_count == 1:
        return [100.0]
    if breakeven_at_t1 and target_count < 2:
        raise HTTPException(status_code=400, detail="Breakeven at T1 requires at least two targets")

    provided = list(values or [])
    allocations: List[float] = [0.0] if breakeven_at_t1 else []
    expected_explicit_count = target_count - 2 if breakeven_at_t1 else target_count - 1
    if breakeven_at_t1 and len(provided) > expected_explicit_count:
        provided = provided[-expected_explicit_count:] if expected_explicit_count > 0 else []
    explicit_count = min(len(provided), expected_explicit_count)
    running_total = 0.0
    for index in range(explicit_count):
        raw = provided[index]
        if raw in {None, ""}:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="target_allocations must contain valid numbers")
        if value < 0:
            raise HTTPException(status_code=400, detail="target_allocations cannot contain negative values")
        running_total += value
        if running_total >= 100:
            raise HTTPException(status_code=400, detail="target_allocations must leave room for the final target")
        allocations.append(round(value, 2))

    while len(allocations) < (1 + expected_explicit_count if breakeven_at_t1 else target_count - 1):
        allocations.append(0.0)
    allocations.append(round(100.0 - sum(allocations), 2))
    if allocations[-1] < 0:
        raise HTTPException(status_code=400, detail="target_allocations exceed 100 percent")
    return allocations


def mid_price_from_quote(quote: dict) -> Optional[float]:
    bid = quote.get("bid")
    ask = quote.get("ask")
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    bid_decimal = Decimal(str(bid))
    ask_decimal = Decimal(str(ask))
    precision = max(-bid_decimal.as_tuple().exponent, -ask_decimal.as_tuple().exponent, 0)
    midpoint = (bid_decimal + ask_decimal) / Decimal("2")
    return float(midpoint.quantize(Decimal(1).scaleb(-precision)))


async def resolve_trade_plan_swing_type(account: dict, symbol: str, strong_swing_price: float, strong_swing_type: Optional[str] = None) -> str:
    normalized = str(strong_swing_type or "").upper().strip()
    if normalized in {"STRONG_LOW", "STRONG_HIGH"}:
        return normalized

    price = await metaapi_service.get_symbol_price(account["api_token"], account["account_id"], str(symbol or "").upper().strip())
    current_price = mid_price_from_quote(price)
    if current_price is None:
        raise HTTPException(status_code=400, detail="Current market price is unavailable for this symbol")
    return "STRONG_HIGH" if float(strong_swing_price) > float(current_price) else "STRONG_LOW"


def derive_trade_plan(
    account: dict,
    symbol: str,
    strong_swing_type: str,
    strong_swing_price: float,
    reversal_points: List[float],
    unmitigated_targets: List[float],
    target_allocations: Optional[List[Optional[float]]] = None,
    breakeven_at_t1: bool = False,
    point_size_override: Optional[float] = None,
    risk_amount_override: Optional[float] = None,
) -> dict:
    normalized_symbol = str(symbol or "").upper().strip()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    try:
        swing_price = float(strong_swing_price)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="strong_swing_price must be a valid number")
    if swing_price <= 0:
        raise HTTPException(status_code=400, detail="strong_swing_price must be positive")

    direction = trade_plan_direction(strong_swing_type)
    normalized_reversals = normalize_float_list(reversal_points, "reversal_points")
    normalized_targets = normalize_float_list(unmitigated_targets, "unmitigated_targets")
    if not normalized_reversals:
        raise HTTPException(status_code=400, detail="At least one reversal point is required")
    if not normalized_targets:
        raise HTTPException(status_code=400, detail="At least one unmitigated target is required")
    if breakeven_at_t1 and len(normalized_targets) < 2:
        raise HTTPException(status_code=400, detail="Breakeven at T1 requires at least two targets")

    point_size = float(point_size_override or 0.0)
    if point_size <= 0:
        point_size = infer_point_size(
            normalized_symbol,
            [swing_price, *normalized_reversals, *normalized_targets],
        )
    entry_buffer = point_size
    stop_buffer = point_size * 3

    if direction == "LONG":
        if any(point <= swing_price for point in normalized_reversals):
            raise HTTPException(status_code=400, detail="For a long plan, reversal points must stay above the strong low")
        entry_price = min(normalized_reversals) - entry_buffer
        stop_loss = swing_price - stop_buffer
        ordered_targets = sorted(normalized_targets)
        if any(target <= entry_price for target in ordered_targets):
            raise HTTPException(status_code=400, detail="For a long plan, targets must be above the entry price")
    else:
        if any(point >= swing_price for point in normalized_reversals):
            raise HTTPException(status_code=400, detail="For a short plan, reversal points must stay below the strong high")
        entry_price = max(normalized_reversals) + entry_buffer
        stop_loss = swing_price + stop_buffer
        ordered_targets = sorted(normalized_targets, reverse=True)
        if any(target >= entry_price for target in ordered_targets):
            raise HTTPException(status_code=400, detail="For a short plan, targets must be below the entry price")

    if direction == "LONG" and stop_loss >= entry_price:
        raise HTTPException(status_code=400, detail="Stop loss must remain below entry for a long plan")
    if direction == "SHORT" and stop_loss <= entry_price:
        raise HTTPException(status_code=400, detail="Stop loss must remain above entry for a short plan")

    if risk_amount_override is None:
        risk_amount = float(account.get("risk_amount") or settings.default_risk_amount)
    else:
        try:
            risk_amount = float(risk_amount_override)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="risk_amount must be a valid number")
        if risk_amount <= 0:
            raise HTTPException(status_code=400, detail="risk_amount must be greater than 0")

    quantity = calc_quantity(
        normalized_symbol,
        risk_amount,
        entry_price,
        stop_loss,
        account_currency=str(account.get("account_currency") or "USD"),
    )
    sl_pips = calc_sl_pips(normalized_symbol, entry_price, stop_loss)
    allocations = normalize_trade_plan_allocations(len(ordered_targets), target_allocations, breakeven_at_t1)
    targets = [
        {
            "target_index": index + 1,
            "price": float(target),
            "rr_ratio": calc_rr(direction, entry_price, stop_loss, float(target)),
            "allocation_percent": allocations[index],
            "breakeven_trigger": bool(breakeven_at_t1 and index == 0),
        }
        for index, target in enumerate(ordered_targets)
    ]
    return {
        "symbol": normalized_symbol,
        "direction": direction,
        "strong_swing_type": str(strong_swing_type).upper().strip(),
        "strong_swing_price": float(swing_price),
        "reversal_points": sorted(normalized_reversals, reverse=(direction == "SHORT")),
        "unmitigated_targets": ordered_targets,
        "entry_price": round(entry_price, 10),
        "stop_loss": round(stop_loss, 10),
        "point_size": point_size,
        "breakeven_at_t1": bool(breakeven_at_t1),
        "risk_amount": risk_amount,
        "quantity": quantity,
        "sl_pips": sl_pips,
        "targets": targets,
    }


def trigger_distance_pips(symbol: str, direction: str, current_price: Optional[float], entry_price: Optional[float]) -> Optional[float]:
    if current_price is None or entry_price is None:
        return None
    try:
        current_value = float(current_price)
        entry_value = float(entry_price)
    except (TypeError, ValueError):
        return None
    pip_size = pip_size_for_symbol(symbol)
    if pip_size <= 0:
        return None
    if str(direction or "").upper() == "LONG":
        if current_value < entry_value:
            return None
        return (current_value - entry_value) / pip_size
    if current_value > entry_value:
        return None
    return (entry_value - current_value) / pip_size


def trade_plan_runtime_now() -> datetime:
    return datetime.utcnow()
