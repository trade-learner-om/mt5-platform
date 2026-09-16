"""Indian F&O contract helpers for the PE→Stock→CE cycle (monthly only)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional


def _last_thursday(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    d = next_month - timedelta(days=1)
    while d.weekday() != 3:
        d -= timedelta(days=1)
    return d


def compute_monthly_expiry(asof: date) -> date:
    """Return the correct NSE monthly expiry (last Thursday) for the given simulation date.

    If asof is on or before the last Thursday of its month, use that expiry.
    If asof is past that Thursday (i.e. the contract has expired), roll to next month.
    """
    expiry = _last_thursday(asof.year, asof.month)
    if asof > expiry:
        if asof.month == 12:
            expiry = _last_thursday(asof.year + 1, 1)
        else:
            expiry = _last_thursday(asof.year, asof.month + 1)
    return expiry


def parse_expiry_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = text.upper().replace("Z", "")
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%b-%Y",
        "%d%b%Y",
        "%Y%m%d",
        "%d-%b-%y",
        "%d%b%y",
    ):
        try:
            return datetime.strptime(cleaned[:20], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned.replace(" ", "T")[:19]).date()
    except ValueError:
        return None


def strike_near(target: float, available_strikes: list[float]) -> Optional[float]:
    strikes = sorted({float(s) for s in available_strikes if s is not None})
    if not strikes:
        return None
    return min(strikes, key=lambda strike: (abs(strike - float(target)), strike))


def _is_monthly_expiry(expiry: date) -> bool:
    """NSE stock options expire on the last Thursday of the month."""
    # Last day of month
    if expiry.month == 12:
        next_month = date(expiry.year + 1, 1, 1)
    else:
        next_month = date(expiry.year, expiry.month + 1, 1)
    last_day = next_month - timedelta(days=1)
    # Walk back to Thursday (weekday 3)
    last_thursday = last_day
    while last_thursday.weekday() != 3:
        last_thursday -= timedelta(days=1)
    return expiry == last_thursday


def monthly_expiries_on_or_after(catalog: list[dict], underlying: str, asof: date) -> list[date]:
    under = str(underlying or "").upper()
    found: set[date] = set()
    for item in catalog:
        if str(item.get("underlying") or "").upper() != under:
            continue
        if str(item.get("instrument_type") or "").upper() != "OPTION":
            continue
        expiry = parse_expiry_date(item.get("expiry"))
        if expiry is None or expiry < asof:
            continue
        if _is_monthly_expiry(expiry):
            found.add(expiry)
    # Fallback: if catalog dates don't align to last-Thursday heuristic, keep all unique
    # expiries that appear only once per month (stock monthly series).
    if not found:
        by_month: dict[tuple[int, int], list[date]] = {}
        for item in catalog:
            if str(item.get("underlying") or "").upper() != under:
                continue
            if str(item.get("instrument_type") or "").upper() != "OPTION":
                continue
            expiry = parse_expiry_date(item.get("expiry"))
            if expiry is None or expiry < asof:
                continue
            by_month.setdefault((expiry.year, expiry.month), []).append(expiry)
        for dates in by_month.values():
            # Prefer the latest expiry in the month (monthly typically later than weeklies).
            found.add(max(dates))
    return sorted(found)


def next_monthly_expiry_on_or_after(catalog: list[dict], underlying: str, asof: date) -> Optional[date]:
    expiries = monthly_expiries_on_or_after(catalog, underlying, asof)
    return expiries[0] if expiries else None


def fno_equity_underlyings(catalog: list[dict]) -> set[str]:
    """Equity underlyings that have at least one NFO option or future."""
    fno_names: set[str] = set()
    for item in catalog:
        exchange = str(item.get("exchange") or "").upper()
        instrument_type = str(item.get("instrument_type") or "").upper()
        underlying = str(item.get("underlying") or "").upper()
        if not underlying:
            continue
        if exchange in {"NFO", "BFO"} or instrument_type in {"OPTION", "FUTURE", "DERIVATIVE"}:
            fno_names.add(underlying)
    return fno_names


def pick_equity(catalog: list[dict], underlying: str) -> Optional[dict]:
    under = str(underlying or "").upper()
    equity_matches = [
        item
        for item in catalog
        if str(item.get("instrument_type") or "").upper() == "EQUITY"
        and (
            str(item.get("symbol") or "").upper() == under
            or str(item.get("underlying") or "").upper() == under
        )
        and str(item.get("exchange") or "").upper() in {"NSE", "BSE", ""}
    ]
    if not equity_matches:
        return None
    # Prefer NSE EQ.
    equity_matches.sort(
        key=lambda item: (
            0 if str(item.get("exchange") or "").upper() == "NSE" else 1,
            str(item.get("symbol") or ""),
        )
    )
    return equity_matches[0]


def _option_candidates(
    catalog: list[dict],
    *,
    underlying: str,
    option_type: str,
    expiry: date,
) -> list[dict]:
    under = str(underlying or "").upper()
    opt = str(option_type or "").upper()
    matches = []
    for item in catalog:
        if str(item.get("underlying") or "").upper() != under:
            continue
        if str(item.get("instrument_type") or "").upper() != "OPTION":
            continue
        if str(item.get("option_type") or "").upper() != opt:
            continue
        item_expiry = parse_expiry_date(item.get("expiry"))
        if item_expiry != expiry:
            continue
        if item.get("strike") is None:
            continue
        matches.append(item)
    return matches


def pick_monthly_option(
    catalog: list[dict],
    *,
    underlying: str,
    option_type: str,
    asof: date,
    spot: float,
    offset_pct: float,
) -> Optional[dict]:
    """Pick monthly PE/CE nearest to spot * (1 + offset_pct). offset_pct e.g. -0.10 or +0.10.

    Uses compute_monthly_expiry(asof) so the simulation always picks the correct
    month's contract (e.g. Jan expiry on Jan 2, Feb expiry on Feb 1) rather than
    searching the live catalog which only contains currently-listed contracts.
    """
    expiry = compute_monthly_expiry(asof)
    candidates = _option_candidates(catalog, underlying=underlying, option_type=option_type, expiry=expiry)
    if not candidates:
        # Computed expiry not in catalog (expired contract). Fall back to nearest listed expiry.
        expiry = next_monthly_expiry_on_or_after(catalog, underlying, asof)
        if expiry is None:
            return None
        candidates = _option_candidates(catalog, underlying=underlying, option_type=option_type, expiry=expiry)
        if not candidates:
            return None
    target = float(spot) * (1.0 + float(offset_pct))
    strike = strike_near(target, [float(item["strike"]) for item in candidates if item.get("strike") is not None])
    if strike is None:
        return None
    chosen = [
        item
        for item in candidates
        if abs(float(item["strike"]) - strike) < 1e-9
    ]
    if not chosen:
        return None
    chosen.sort(key=lambda item: str(item.get("symbol") or ""))
    return chosen[0]


def pick_monthly_pe(catalog: list[dict], underlying: str, asof: date, spot: float) -> Optional[dict]:
    return pick_monthly_option(
        catalog,
        underlying=underlying,
        option_type="PE",
        asof=asof,
        spot=spot,
        offset_pct=-0.10,
    )


def pick_monthly_ce(catalog: list[dict], underlying: str, asof: date, spot: float) -> Optional[dict]:
    return pick_monthly_option(
        catalog,
        underlying=underlying,
        option_type="CE",
        asof=asof,
        spot=spot,
        offset_pct=0.10,
    )


def lot_size_for(item: Optional[dict], fallback: int = 1) -> int:
    if not item:
        return max(1, int(fallback))
    try:
        size = int(item.get("lot_size") or fallback or 1)
    except (TypeError, ValueError):
        size = fallback
    return max(1, size)
