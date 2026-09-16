from __future__ import annotations

from typing import Any, Optional

from .master_break_levels import as_float
from .risk import calc_pnl_from_price_move, calc_quantity, calc_quantity_from_live_pip_value


def quantity_from_risk(
    risk_amount: float,
    entry: float,
    stop_loss: float,
    symbol_spec: Optional[dict[str, Any]] = None,
    live_ctx: Optional[dict[str, Any]] = None,
    *,
    symbol: str = "XAUUSD",
    account_currency: str = "USD",
) -> float:
    """Size volume from risk vs SL distance using live pip context when available."""
    spec = dict(symbol_spec or {})
    volume_step = as_float(spec.get("volumeStep") or spec.get("volume_step"), 0.01) or 0.01
    volume_min = as_float(spec.get("volumeMin") or spec.get("volume_min"), 0.01) or 0.01
    volume_max_raw = spec.get("volumeMax") if spec.get("volumeMax") is not None else spec.get("volume_max")
    volume_max = as_float(volume_max_raw)
    contract_raw = as_float(spec.get("contractSize") or spec.get("contract_size"))
    contract_size = contract_raw or None
    broker_symbol = str(spec.get("symbol") or symbol or "XAUUSD")
    risk = as_float(risk_amount)
    entry_px = as_float(entry)
    stop_px = as_float(stop_loss)

    volume = 0.0
    if live_ctx:
        live_contract = as_float(live_ctx.get("contract_size"), contract_raw)
        volume = calc_quantity_from_live_pip_value(
            broker_symbol,
            risk,
            entry_px,
            stop_px,
            as_float(live_ctx.get("pip_value_per_standard_lot")),
            volume_step=as_float(live_ctx.get("volume_step"), volume_step) or volume_step,
            volume_min=as_float(live_ctx.get("volume_min"), volume_min) or volume_min,
            volume_max=as_float(live_ctx.get("volume_max"), volume_max),
            tick_size=as_float(live_ctx.get("tick_size")),
            tick_value=as_float(live_ctx.get("tick_value")),
            contract_size=live_contract or None,
            account_currency=str(live_ctx.get("account_currency") or account_currency or "USD"),
            quote_to_account_rate=live_ctx.get("quote_to_account_rate"),
        )
    if volume <= 0:
        volume = calc_quantity(
            broker_symbol,
            risk,
            entry_px,
            stop_px,
            account_currency=str((live_ctx or {}).get("account_currency") or account_currency or "USD"),
            quote_to_account_rate=(live_ctx or {}).get("quote_to_account_rate"),
            contract_size=contract_size,
            volume_step=volume_step,
            volume_min=volume_min,
            volume_max=volume_max or None,
        )
    return as_float(volume)


def pnl_from_fill(
    side: str,
    entry: float,
    exit_price: float,
    quantity_lots: float,
    symbol_spec: Optional[dict[str, Any]] = None,
    *,
    symbol: str = "XAUUSD",
    account_currency: str = "USD",
    live_ctx: Optional[dict[str, Any]] = None,
) -> float:
    """Account-currency PnL aligned with quantity_from_risk / calc_quantity sizing."""
    spec = dict(symbol_spec or {})
    broker_symbol = str(spec.get("symbol") or symbol or "XAUUSD")
    contract_size = as_float(spec.get("contractSize") or spec.get("contract_size")) or None
    ctx = live_ctx or {}
    if ctx.get("contract_size") is not None:
        contract_size = as_float(ctx.get("contract_size"), contract_size) or contract_size
    return as_float(
        calc_pnl_from_price_move(
            broker_symbol,
            side,
            as_float(entry),
            as_float(exit_price),
            as_float(quantity_lots),
            pip_value_per_standard_lot=as_float(ctx.get("pip_value_per_standard_lot")) or None,
            contract_size=contract_size,
            account_currency=str(ctx.get("account_currency") or account_currency or "USD"),
            quote_to_account_rate=ctx.get("quote_to_account_rate"),
        )
    )
