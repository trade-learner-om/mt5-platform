import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Optional, Union


KNOWN_CURRENCY_CODES = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "NZD",
    "CAD",
    "CHF",
    "SGD",
    "HKD",
    "NOK",
    "SEK",
    "DKK",
    "ZAR",
    "MXN",
    "CNH",
    "PLN",
    "TRY",
    "HUF",
    "CZK",
}


def _extract_symbol_letters(symbol: str) -> str:
    return "".join(char for char in str(symbol or "").upper() if char.isalpha())


def is_gold_symbol(symbol: str) -> bool:
    upper = _extract_symbol_letters(symbol)
    return "XAU" in upper or "GOLD" in upper


def _decimal_places(value: Optional[Union[float, str, Decimal]]) -> int:
    if value in {None, ""}:
        return 0
    try:
        decimal_value = Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError, TypeError):
        return 0
    exponent = decimal_value.as_tuple().exponent
    return max(-exponent, 0)


def digits_from_symbol_spec(symbol_spec: Optional[dict]) -> int:
    spec = symbol_spec or {}
    digits = spec.get("digits")
    if digits is not None:
        try:
            return max(0, min(int(digits), 10))
        except (TypeError, ValueError):
            pass
    tick_size = point_size_from_symbol_spec(spec)
    if tick_size > 0:
        return max(0, min(_decimal_places(tick_size), 10))
    return 5


def point_size_from_symbol_spec(symbol_spec: Optional[dict]) -> float:
    spec = symbol_spec or {}
    tick_size = float(spec.get("tickSize") or spec.get("trade_tick_size") or 0.0)
    if tick_size > 0:
        return tick_size
    point = float(spec.get("point") or 0.0)
    if point > 0:
        return point
    digits = spec.get("digits")
    if digits is not None:
        try:
            digits_i = int(digits)
        except (TypeError, ValueError):
            digits_i = -1
        if digits_i >= 0:
            return 10 ** (-digits_i)
    return 0.0


def normalize_price_to_symbol(value: Optional[float], symbol_spec: Optional[dict] = None) -> float:
    """
    Align a price to the broker symbol tick grid and decimal precision.

    MT5 rejects off-grid prices with retcode 10015 (Invalid price).
    """
    if value is None:
        return 0.0
    try:
        price = float(value)
    except (TypeError, ValueError):
        return 0.0
    if price <= 0:
        return price

    spec = symbol_spec or {}
    tick_size = point_size_from_symbol_spec(spec)
    if tick_size <= 0:
        tick_size = 0.00001

    digits = spec.get("digits")
    if digits is not None:
        try:
            digits_i = max(0, min(int(digits), 10))
        except (TypeError, ValueError):
            digits_i = max(0, _decimal_places(tick_size))
    else:
        digits_i = max(0, _decimal_places(tick_size))

    tick_decimal = Decimal(str(tick_size))
    price_decimal = Decimal(str(price))
    ticks = (price_decimal / tick_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    normalized = (ticks * tick_decimal).quantize(Decimal(1).scaleb(-digits_i), rounding=ROUND_HALF_UP)
    return float(normalized)


def infer_point_size(symbol: str, reference_values: Optional[Iterable[float]] = None, symbol_spec: Optional[dict] = None) -> float:
    spec_size = point_size_from_symbol_spec(symbol_spec)
    if spec_size > 0:
        return spec_size

    max_decimals = 0
    for value in reference_values or []:
        max_decimals = max(max_decimals, _decimal_places(value))
    if max_decimals > 0:
        return 10 ** (-max_decimals)

    _, quote = parse_fx_symbol(symbol)
    if quote == "JPY":
        return 0.001
    return 0.00001


def pip_size_for_symbol(symbol: str) -> float:
    base, quote = parse_fx_symbol(symbol)
    if base == "XAU":
        return 0.10
    if quote == "JPY":
        return 0.01
    return 0.0001


def is_forex_symbol(symbol: str) -> bool:
    base, quote = parse_fx_symbol(symbol)
    return base in KNOWN_CURRENCY_CODES and quote in KNOWN_CURRENCY_CODES


def symbol_uses_pips(symbol: str) -> bool:
    return is_gold_symbol(symbol) or is_forex_symbol(symbol)


def parse_fx_symbol(symbol: str) -> tuple[str, str]:
    upper = _extract_symbol_letters(symbol)
    if "XAU" in upper:
        xau_index = upper.find("XAU")
        quote = upper[xau_index + 3:xau_index + 6] if len(upper) >= (xau_index + 6) else "USD"
        return ("XAU", quote if len(quote) == 3 else "USD")
    if len(upper) < 6:
        return ("", "")
    for index in range(0, len(upper) - 5):
        base = upper[index:index + 3]
        quote = upper[index + 3:index + 6]
        if base in KNOWN_CURRENCY_CODES and quote in KNOWN_CURRENCY_CODES:
            return (base, quote)
    return (upper[:3], upper[3:6])


def contract_size_for_symbol(symbol: str, symbol_spec: Optional[dict] = None) -> float:
    if symbol_spec:
        contract_size = float(symbol_spec.get("contractSize") or symbol_spec.get("tradeContractSize") or 0.0)
        if contract_size > 0:
            return contract_size
    base, _ = parse_fx_symbol(symbol)
    if base == "XAU":
        return 100.0
    if is_forex_symbol(symbol):
        return 100000.0
    return 1.0


def calc_sl_pips(symbol: str, entry: float, stop_loss: float) -> float:
    distance = abs(float(entry or 0.0) - float(stop_loss or 0.0))
    if symbol_uses_pips(symbol):
        pip_size = pip_size_for_symbol(symbol)
        return round(distance / pip_size, 2)
    precision = min(10, max(2, _decimal_places(entry), _decimal_places(stop_loss)))
    return round(distance, precision)


def calc_rr(side: str, entry: float, stop_loss: float, target: Optional[float]) -> Optional[float]:
    if target is None:
        return None
    risk = abs(entry - stop_loss)
    reward = abs(target - entry)
    if risk == 0:
        return None
    return round(reward / risk, 2)


def calc_quantity(
    symbol: str,
    risk_amount: float,
    entry: float,
    stop_loss: float,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
    contract_size: Optional[float] = None,
    volume_step: float = 0.01,
    volume_min: float = 0.01,
    volume_max: Optional[float] = None,
) -> float:
    stop_distance = abs(float(entry or 0.0) - float(stop_loss or 0.0))
    if stop_distance <= 0:
        return 0
    if symbol_uses_pips(symbol):
        sl_pips = calc_sl_pips(symbol, entry, stop_loss)
        if sl_pips <= 0:
            return 0
        pip_value_per_standard_lot = infer_pip_value_per_standard_lot(
            symbol,
            entry,
            account_currency=account_currency,
            quote_to_account_rate=quote_to_account_rate,
            contract_size=contract_size,
        )
        lots = risk_amount / (sl_pips * pip_value_per_standard_lot)
    else:
        price_value_per_standard_lot = infer_price_value_per_standard_lot(
            symbol,
            entry,
            account_currency=account_currency,
            quote_to_account_rate=quote_to_account_rate,
            contract_size=contract_size,
        )
        if price_value_per_standard_lot <= 0:
            return 0
        lots = risk_amount / (stop_distance * price_value_per_standard_lot)
    return normalize_volume_to_risk(lots, volume_step=volume_step, volume_min=volume_min, volume_max=volume_max)


def calc_quantity_from_live_pip_value(
    symbol: str,
    risk_amount: float,
    entry: float,
    stop_loss: float,
    pip_value_per_standard_lot: float,
    volume_step: float = 0.01,
    volume_min: float = 0.01,
    volume_max: Optional[float] = None,
    tick_size: Optional[float] = None,
    tick_value: Optional[float] = None,
    contract_size: Optional[float] = None,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
) -> float:
    stop_distance = abs(float(entry or 0.0) - float(stop_loss or 0.0))
    if stop_distance <= 0:
        return 0
    if symbol_uses_pips(symbol):
        sl_pips = calc_sl_pips(symbol, entry, stop_loss)
        if sl_pips <= 0 or pip_value_per_standard_lot <= 0:
            return 0
        lots = risk_amount / (sl_pips * pip_value_per_standard_lot)
    else:
        effective_tick_size = float(tick_size or 0.0)
        effective_tick_value = float(tick_value or 0.0)
        price_value_per_standard_lot = 0.0
        if effective_tick_size > 0 and effective_tick_value > 0:
            price_value_per_standard_lot = effective_tick_value / effective_tick_size
        if price_value_per_standard_lot <= 0:
            price_value_per_standard_lot = infer_price_value_per_standard_lot(
                symbol,
                entry,
                account_currency=account_currency,
                quote_to_account_rate=quote_to_account_rate,
                contract_size=contract_size,
            )
        if price_value_per_standard_lot <= 0:
            return 0
        lots = risk_amount / (stop_distance * price_value_per_standard_lot)
    return normalize_volume_to_risk(lots, volume_step=volume_step, volume_min=volume_min, volume_max=volume_max)


def calc_risk_amount_from_quantity(
    symbol: str,
    quantity: float,
    entry: float,
    stop_loss: float,
    *,
    pip_value_per_standard_lot: Optional[float] = None,
    tick_size: Optional[float] = None,
    tick_value: Optional[float] = None,
    contract_size: Optional[float] = None,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
) -> float:
    """Inverse of quantity sizing: risk ≈ lots × SL distance × value-per-lot."""
    lots = float(quantity or 0.0)
    stop_distance = abs(float(entry or 0.0) - float(stop_loss or 0.0))
    if lots <= 0 or stop_distance <= 0:
        return 0.0
    if symbol_uses_pips(symbol):
        sl_pips = calc_sl_pips(symbol, entry, stop_loss)
        if sl_pips <= 0:
            return 0.0
        pip_value = float(pip_value_per_standard_lot or 0.0)
        if pip_value <= 0:
            pip_value = infer_pip_value_per_standard_lot(
                symbol,
                entry,
                account_currency=account_currency,
                quote_to_account_rate=quote_to_account_rate,
                contract_size=contract_size,
            )
        if pip_value <= 0:
            return 0.0
        return round(lots * sl_pips * pip_value, 2)
    effective_tick_size = float(tick_size or 0.0)
    effective_tick_value = float(tick_value or 0.0)
    price_value_per_standard_lot = 0.0
    if effective_tick_size > 0 and effective_tick_value > 0:
        price_value_per_standard_lot = effective_tick_value / effective_tick_size
    if price_value_per_standard_lot <= 0:
        price_value_per_standard_lot = infer_price_value_per_standard_lot(
            symbol,
            entry,
            account_currency=account_currency,
            quote_to_account_rate=quote_to_account_rate,
            contract_size=contract_size,
        )
    if price_value_per_standard_lot <= 0:
        return 0.0
    return round(lots * stop_distance * price_value_per_standard_lot, 2)


def normalize_volume_to_risk(
    raw_lots: float,
    volume_step: float = 0.01,
    volume_min: float = 0.01,
    volume_max: Optional[float] = None,
) -> float:
    """
    Floor volume to the broker step so stop-loss risk never exceeds the configured risk.
    Returns 0 when the calculated size is below the broker minimum.
    """
    lots = float(raw_lots or 0.0)
    step = float(volume_step or 0.01)
    minimum = float(volume_min or step)
    maximum = float(volume_max or 0.0)
    if lots <= 0 or step <= 0:
        return 0.0
    floored = math.floor((lots + 1e-12) / step) * step
    if maximum > 0:
        floored = min(floored, maximum)
    if floored + 1e-12 < minimum:
        return 0.0
    decimals = max(0, _decimal_places(step))
    return round(floored, decimals)


def infer_quote_to_account_rate(symbol: str, reference_price: float, account_currency: str = "USD") -> float:
    normalized_reference = float(reference_price or 0.0)
    if normalized_reference <= 0:
        return 0.0
    base, quote = parse_fx_symbol(symbol)
    normalized_account_currency = str(account_currency or "USD").upper()
    if not quote:
        return 0.0
    if quote == normalized_account_currency:
        return 1.0
    if base == normalized_account_currency:
        return 1.0 / normalized_reference
    return 0.0


def infer_pip_value_per_standard_lot(
    symbol: str,
    reference_price: float,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
    contract_size: Optional[float] = None,
) -> float:
    """
    Best-effort account-currency fallback when live broker pip value is unavailable.
    """
    normalized_reference = float(reference_price or 0.0)
    if normalized_reference <= 0:
        base, _ = parse_fx_symbol(symbol)
        return 1.0 if base == "XAU" else 10.0
    _, quote = parse_fx_symbol(symbol)
    pip_size = pip_size_for_symbol(symbol)
    standard_lot_units = contract_size_for_symbol(symbol, None if contract_size is None else {"contractSize": contract_size})
    quote_currency_pip_value = pip_size * standard_lot_units
    effective_rate = float(quote_to_account_rate or 0.0)
    if effective_rate <= 0:
        effective_rate = infer_quote_to_account_rate(symbol, normalized_reference, account_currency=account_currency)
    if quote == str(account_currency or "USD").upper():
        return quote_currency_pip_value
    if effective_rate > 0:
        return quote_currency_pip_value * effective_rate
    base, _ = parse_fx_symbol(symbol)
    return 1.0 if base == "XAU" else 10.0


def infer_price_value_per_standard_lot(
    symbol: str,
    reference_price: float,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
    contract_size: Optional[float] = None,
) -> float:
    effective_contract_size = contract_size_for_symbol(symbol, None if contract_size is None else {"contractSize": contract_size})
    effective_rate = float(quote_to_account_rate or 0.0)
    if effective_rate <= 0:
        effective_rate = infer_quote_to_account_rate(symbol, float(reference_price or 0.0), account_currency=account_currency)
    if effective_rate > 0:
        return effective_contract_size * effective_rate
    return effective_contract_size


def calc_pnl_from_price_move(
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    quantity_lots: float,
    pip_value_per_standard_lot: Optional[float] = None,
    contract_size: Optional[float] = None,
    account_currency: str = "USD",
    quote_to_account_rate: Optional[float] = None,
) -> float:
    normalized_entry = float(entry_price or 0.0)
    normalized_exit = float(exit_price or 0.0)
    normalized_lots = float(quantity_lots or 0.0)
    if normalized_entry <= 0 or normalized_exit <= 0 or normalized_lots <= 0:
        return 0.0
    normalized_side = str(side or "").upper()
    is_long = normalized_side in {"LONG", "BUY"}
    price_move = (
        normalized_exit - normalized_entry
        if is_long
        else normalized_entry - normalized_exit
    )
    effective_contract_size = contract_size_for_symbol(symbol, None if contract_size is None else {"contractSize": contract_size})
    effective_quote_to_account_rate = float(quote_to_account_rate or 0.0)
    if effective_quote_to_account_rate <= 0:
        effective_quote_to_account_rate = infer_quote_to_account_rate(symbol, normalized_exit, account_currency=account_currency)
    if effective_quote_to_account_rate > 0:
        pnl_in_quote = price_move * normalized_lots * effective_contract_size
        return round(pnl_in_quote * effective_quote_to_account_rate, 2)
    pip_size = pip_size_for_symbol(symbol)
    if pip_size <= 0:
        return 0.0
    effective_pip_value = float(pip_value_per_standard_lot or 0.0)
    if effective_pip_value <= 0:
        effective_pip_value = infer_pip_value_per_standard_lot(
            symbol,
            normalized_exit,
            account_currency=account_currency,
            contract_size=effective_contract_size,
        )
    pip_move = price_move / pip_size
    return round(pip_move * normalized_lots * effective_pip_value, 2)
