from typing import Any, Mapping, Optional


def format_log_price(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    if number <= 0:
        return None
    text = f"{number:.5f}".rstrip("0").rstrip(".")
    return text or f"{number:g}"


def order_price_fields(
    source: Optional[Mapping[str, Any]] = None,
    *,
    entry: Any = None,
    stop_loss: Any = None,
    target: Any = None,
    side: Any = None,
    quantity: Any = None,
    bid: Any = None,
    ask: Any = None,
) -> dict:
    doc = source or {}
    resolved = {
        "side": side if side is not None else doc.get("side"),
        "entry": entry if entry is not None else doc.get("entry", doc.get("price")),
        "stop_loss": stop_loss if stop_loss is not None else doc.get("stop_loss", doc.get("sl")),
        "target": target if target is not None else doc.get("target", doc.get("tp")),
        "quantity": quantity if quantity is not None else doc.get("quantity", doc.get("volume")),
        "bid": bid if bid is not None else doc.get("bid"),
        "ask": ask if ask is not None else doc.get("ask"),
    }
    payload = {}
    if resolved["side"]:
        payload["side"] = str(resolved["side"]).upper()
    for key, value in resolved.items():
        if key == "side":
            continue
        if value is not None and value != "":
            payload[key] = value
    return payload


def format_order_log_prices(
    source: Optional[Mapping[str, Any]] = None,
    **kwargs,
) -> str:
    fields = order_price_fields(source, **kwargs)
    parts = []
    if fields.get("side"):
        parts.append(str(fields["side"]))
    entry = format_log_price(fields.get("entry"))
    if entry:
        parts.append(f"entry {entry}")
    stop_loss = format_log_price(fields.get("stop_loss"))
    if stop_loss:
        parts.append(f"SL {stop_loss}")
    target = format_log_price(fields.get("target"))
    if target:
        parts.append(f"TP {target}")
    quantity = fields.get("quantity")
    if quantity is not None:
        try:
            qty_number = float(quantity)
            if qty_number > 0:
                parts.append(f"qty {qty_number:g}")
        except (TypeError, ValueError):
            pass
    bid = format_log_price(fields.get("bid"))
    ask = format_log_price(fields.get("ask"))
    if bid or ask:
        parts.append(f"bid {bid or '-'} ask {ask or '-'}")
    return " · ".join(parts)


def append_order_log_prices(message: str, source: Optional[Mapping[str, Any]] = None, **kwargs) -> str:
    suffix = format_order_log_prices(source, **kwargs)
    if not suffix:
        return message
    return f"{message} · {suffix}"


def merge_order_log_payload(payload: Optional[dict] = None, source: Optional[Mapping[str, Any]] = None, **kwargs) -> dict:
    merged = dict(payload or {})
    merged.update(order_price_fields(source, **kwargs))
    return merged
