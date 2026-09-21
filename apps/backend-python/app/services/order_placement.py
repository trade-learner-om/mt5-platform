from typing import Any, Optional
import logging

from .order_logging import append_order_log_prices

logger = logging.getLogger(__name__)

SL_LIMIT_FALLBACK_REASON = (
    "SL (stop-entry) was rejected as Invalid price for the current market. "
    "Placed a LIMIT order at the same entry, stop loss, target, and quantity instead."
)


def is_invalid_price_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "invalid price" in text or "retcode=10015" in text or " 10015" in text


def is_market_closed_error(exc: BaseException) -> bool:
    """MT5 retcode 10018: the venue is closed, so retry once quotes resume."""
    text = str(exc).lower()
    return "market closed" in text or "retcode=10018" in text or " 10018" in text


def build_sl_limit_fallback_info(sl_error: str) -> dict:
    return {
        "requested_order_type": "SL",
        "placed_order_type": "LIMIT",
        "sl_placement_error": sl_error,
        "fallback_reason": SL_LIMIT_FALLBACK_REASON,
    }


def sl_limit_fallback_activity_message(symbol: str, sl_error: str, *, retry: bool = False) -> str:
    label = f"{symbol} retry" if retry else str(symbol or "Order")
    return (
        f"{label}: SL rejected ({sl_error}). "
        "Placed LIMIT at same entry/SL/target — stop-entry was invalid vs live bid/ask."
    )


def sl_limit_fallback_event_message(symbol: str, sl_error: str, source: Optional[dict] = None, *, retry: bool = False) -> str:
    return append_order_log_prices(sl_limit_fallback_activity_message(symbol, sl_error, retry=retry), source)


def order_placement_fallback_fields(fallback: Optional[dict]) -> dict:
    if not fallback:
        return {}
    return {
        "order_type": fallback.get("placed_order_type", "LIMIT"),
        "placement_fallback_reason": fallback.get("fallback_reason"),
        "placement_sl_error": fallback.get("sl_placement_error"),
    }


async def place_pending_order_with_limit_fallback(service, token: str, account_id: str, payload: dict) -> dict[str, Any]:
    order_type = str(payload.get("order_type") or "").upper()
    if order_type != "SL":
        result = await service.place_pending_order(token, account_id, payload)
        return {"result": result, "order_type": order_type, "fallback": None}

    try:
        result = await service.place_pending_order(token, account_id, payload)
        return {"result": result, "order_type": "SL", "fallback": None}
    except Exception as exc:
        if not is_invalid_price_error(exc):
            raise
        sl_error = str(exc)
        logger.info(
            "SL Invalid price; attempting LIMIT fallback | symbol=%s side=%s entry=%s stop_loss=%s error=%s",
            payload.get("symbol"),
            payload.get("side"),
            payload.get("entry"),
            payload.get("stop_loss"),
            sl_error,
        )
        limit_payload = {**payload, "order_type": "LIMIT"}
        result = await service.place_pending_order(token, account_id, limit_payload)
        return {
            "result": result,
            "order_type": "LIMIT",
            "fallback": build_sl_limit_fallback_info(sl_error),
        }
