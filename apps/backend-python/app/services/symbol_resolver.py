from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

CANONICAL_GOLD = "GOLD"
GOLD_REQUEST_ALIASES = frozenset({"GOLD", "XAUUSD", "XAU/USD", "XAU-USD"})
AUTO_DETECT_CANONICALS = (CANONICAL_GOLD, "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD")
FOREX_PAIR_PATTERN = re.compile(r"^[A-Z]{6}$")


def normalize_symbol(value: str) -> str:
    return str(value or "").upper().strip().replace("/", "").replace("-", "")


def lookup_live_price(live_prices: dict, symbol: str) -> dict:
    return live_prices.get(normalize_symbol(symbol), {}) or {}


def is_gold_request(symbol: str) -> bool:
    normalized = normalize_symbol(symbol)
    return normalized in GOLD_REQUEST_ALIASES or "XAU" in normalized or normalized == "GOLD"


def infer_canonical(symbol: str) -> Optional[str]:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return None
    if is_gold_request(normalized):
        return CANONICAL_GOLD
    if FOREX_PAIR_PATTERN.match(normalized):
        return normalized
    return None


def default_gold_symbol(available_symbols: list[str]) -> str:
    normalized_pairs = [(normalize_symbol(symbol), str(symbol)) for symbol in available_symbols if str(symbol or "").strip()]
    normalized = [item[0] for item in normalized_pairs]
    for preferred in ("XAUUSD", "GOLD"):
        if preferred in normalized:
            return next(original for norm, original in normalized_pairs if norm == preferred)
    for norm, original in normalized_pairs:
        if norm.startswith("XAUUSD"):
            return original
    match = next((original for norm, original in normalized_pairs if "XAU" in norm or "GOLD" in norm), "")
    return match or "XAUUSD"


def _account_aliases(account: Optional[dict]) -> dict[str, str]:
    if not account:
        return {}
    aliases = account.get("symbol_aliases") or {}
    return {normalize_symbol(key): normalize_symbol(value) for key, value in aliases.items() if str(key or "").strip() and str(value or "").strip()}


def _alias_for_request(account: Optional[dict], requested: str) -> Optional[str]:
    aliases = _account_aliases(account)
    canonical = infer_canonical(requested) or normalize_symbol(requested)
    return aliases.get(canonical)


def _resolve_gold(requested: str, available: set[str], account: Optional[dict]) -> Optional[str]:
    alias = _alias_for_request(account, requested)
    if alias and alias in available:
        return alias
    resolved = default_gold_symbol(sorted(available))
    return resolved if resolved in available else None


def _resolve_forex(requested: str, available: set[str], account: Optional[dict]) -> Optional[str]:
    normalized = normalize_symbol(requested)
    alias = _alias_for_request(account, requested)
    if alias and alias in available:
        return alias
    if normalized in available:
        return normalized
    prefix_matches = sorted(symbol for symbol in available if symbol.startswith(normalized))
    if prefix_matches:
        return prefix_matches[0]
    return None


def resolve_broker_symbol(
    requested: str,
    available_symbols: list[str],
    account: Optional[dict] = None,
) -> str:
    normalized_requested = normalize_symbol(requested)
    if not normalized_requested:
        raise HTTPException(status_code=400, detail="Symbol is required.")
    original_by_normalized = {}
    for symbol in available_symbols:
        normalized = normalize_symbol(symbol)
        if normalized and normalized not in original_by_normalized:
            original_by_normalized[normalized] = str(symbol)
    available = set(original_by_normalized.keys())
    if not available:
        raise HTTPException(status_code=400, detail="Broker symbol list is unavailable.")

    def pick(normalized: str) -> str:
        return original_by_normalized[normalized]

    if normalized_requested in available:
        return pick(normalized_requested)

    alias = _alias_for_request(account, normalized_requested)
    if alias and alias in available:
        return pick(alias)

    if is_gold_request(normalized_requested):
        resolved = _resolve_gold(normalized_requested, available, account)
        if resolved:
            return pick(resolved)
        suggestions = suggest_symbols("XAU", available_symbols, limit=5)
        suffix = f" Closest matches: {', '.join(suggestions)}." if suggestions else ""
        raise HTTPException(
            status_code=400,
            detail=f"No GOLD/XAUUSD symbol is available on the selected broker account.{suffix}",
        )

    if FOREX_PAIR_PATTERN.match(normalized_requested):
        resolved = _resolve_forex(normalized_requested, available, account)
        if resolved:
            return pick(resolved)
        suggestions = suggest_symbols(normalized_requested[:3], available_symbols, limit=5)
        suffix = f" Closest matches: {', '.join(suggestions)}." if suggestions else ""
        raise HTTPException(
            status_code=400,
            detail=f"{normalized_requested} is not available on the selected broker account.{suffix}",
        )

    suggestions = suggest_symbols(normalized_requested[:3], available_symbols, limit=5)
    suffix = f" Closest matches: {', '.join(suggestions)}." if suggestions else ""
    raise HTTPException(
        status_code=400,
        detail=f"{normalized_requested} is not available on the selected broker account.{suffix}",
    )


def suggest_symbols(query: str, available_symbols: list[str], limit: int = 12) -> list[str]:
    needle = normalize_symbol(query)
    if not needle:
        return []
    starts = [symbol for symbol in available_symbols if normalize_symbol(symbol).startswith(needle)]
    contains = [symbol for symbol in available_symbols if needle in normalize_symbol(symbol) and not normalize_symbol(symbol).startswith(needle)]
    return (starts + contains)[:limit]


def build_auto_detect_aliases(available_symbols: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for canonical in AUTO_DETECT_CANONICALS:
        try:
            resolved = resolve_broker_symbol(canonical, available_symbols, account={"symbol_aliases": {}})
        except HTTPException:
            continue
        aliases[canonical] = resolved
    return aliases


def display_symbol(requested: str, broker_symbol: str) -> str:
    canonical = infer_canonical(requested) or normalize_symbol(requested)
    broker = normalize_symbol(broker_symbol)
    if canonical == CANONICAL_GOLD and broker != canonical:
        return f"GOLD ({broker})"
    if canonical and broker != canonical:
        return f"{canonical} ({broker})"
    return broker


async def fetch_available_symbols(account: dict) -> list[str]:
    from .metaapi_client import metaapi_service

    symbols = await metaapi_service.get_symbols(account["api_token"], account["account_id"])
    return [str(symbol) for symbol in symbols if str(symbol or "").strip()]


async def resolve_broker_symbol_for_account(account: dict, requested: str) -> str:
    available = await fetch_available_symbols(account)
    return resolve_broker_symbol(requested, available, account)


async def detect_account_symbol_aliases(account: dict) -> dict[str, str]:
    available = await fetch_available_symbols(account)
    return build_auto_detect_aliases(available)
