"""Shared MT5 pending-order type/side inference for broker order dicts."""

from __future__ import annotations


def infer_order_type_and_side(broker_order: dict) -> tuple[str, str]:
    raw_type = str(broker_order.get("type") or "").upper()
    numeric_type_map = {
        "0": ("MARKET", "BUY"),
        "1": ("MARKET", "SELL"),
        "2": ("LIMIT", "BUY"),
        "3": ("LIMIT", "SELL"),
        "4": ("SL", "BUY"),
        "5": ("SL", "SELL"),
        "6": ("SL", "BUY"),
        "7": ("SL", "SELL"),
    }
    if raw_type in numeric_type_map:
        return numeric_type_map[raw_type]
    if "SELL" in raw_type:
        side = "SELL"
    else:
        side = "BUY"
    if "LIMIT" in raw_type:
        order_type = "LIMIT"
    elif "STOP" in raw_type:
        order_type = "SL"
    else:
        order_type = "MARKET"
    return order_type, side
