"""Unmitigated swing analyze + execute session helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from bson import ObjectId

from .analytics.market_structure import DEFAULT_SWING_LENGTH
from .candle_history import get_recent_chart_candles, get_unmitigated_levels_for_symbol, normalize_timeframe
from .scheduled_trade_levels import PRICE_EPSILON, MIN_TARGET_R, as_float, resolve_side_from_level, usable_target

STRUCTURE_TIMEFRAMES = frozenset({"H4", "H1", "M15"})
SESSION_COLLECTION = "structure_swing_sessions"
SOURCE_UNMITIGATED_SWINGS = "unmitigated_swings"


def normalize_structure_timeframe(value: str) -> str:
    normalized = normalize_timeframe(value)
    if normalized not in STRUCTURE_TIMEFRAMES:
        raise ValueError("Unsupported structure timeframe (use H4, H1, or M15)")
    return normalized


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _level_row(price: float, time_value: Any = None, index: Any = None, status: str = "Active") -> dict[str, Any]:
    return {
        "price": float(price),
        "time": _iso(time_value) if not isinstance(time_value, str) else time_value,
        "index": int(index) if index is not None else None,
        "status": status,
    }


def slice_highs_and_lows(
    levels: Sequence[dict[str, Any]],
    *,
    swing_count: int,
    mid_price: Optional[float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pick up to N resistances and N supports nearest the live mid (or extremes)."""
    count = max(1, min(int(swing_count), 50))
    highs_raw = [item for item in levels if item.get("kind") == "high" and not item.get("mitigated")]
    lows_raw = [item for item in levels if item.get("kind") == "low" and not item.get("mitigated")]
    mid = as_float(mid_price) if mid_price is not None else 0.0

    if mid > 0:
        above = [item for item in highs_raw if as_float(item.get("price")) > mid + PRICE_EPSILON]
        below = [item for item in lows_raw if as_float(item.get("price")) < mid - PRICE_EPSILON]
        above.sort(key=lambda item: as_float(item.get("price")) - mid)
        below.sort(key=lambda item: mid - as_float(item.get("price")))
        chosen_highs = above[:count]
        chosen_lows = below[:count]
        if len(chosen_highs) < count:
            rest = [item for item in highs_raw if item not in chosen_highs]
            rest.sort(key=lambda item: as_float(item.get("price")), reverse=True)
            chosen_highs.extend(rest[: count - len(chosen_highs)])
        if len(chosen_lows) < count:
            rest = [item for item in lows_raw if item not in chosen_lows]
            rest.sort(key=lambda item: as_float(item.get("price")))
            chosen_lows.extend(rest[: count - len(chosen_lows)])
    else:
        highs_raw.sort(key=lambda item: as_float(item.get("price")), reverse=True)
        lows_raw.sort(key=lambda item: as_float(item.get("price")))
        chosen_highs = highs_raw[:count]
        chosen_lows = lows_raw[:count]

    highs = [
        _level_row(as_float(item.get("price")), item.get("time"), item.get("index"), "Active")
        for item in chosen_highs
    ]
    lows = [
        _level_row(as_float(item.get("price")), item.get("time"), item.get("index"), "Active")
        for item in chosen_lows
    ]
    highs.sort(key=lambda item: item["price"], reverse=True)
    lows.sort(key=lambda item: item["price"], reverse=True)
    return highs, lows


def target_4r_price(side: str, entry: float, stop_loss: float) -> Optional[float]:
    entry_f = as_float(entry)
    stop_f = as_float(stop_loss)
    risk = abs(entry_f - stop_f)
    if risk <= PRICE_EPSILON:
        return None
    if str(side or "").upper() == "SELL":
        return entry_f - (MIN_TARGET_R * risk)
    return entry_f + (MIN_TARGET_R * risk)


def resolve_unmitigated_swing_target(
    side: str,
    entry: float,
    stop_loss: float,
    structure_extreme: Optional[float],
) -> Optional[float]:
    """Farther of 4R vs prior structure-TF candle extreme (BUY max / SELL min)."""
    four_r = target_4r_price(side, entry, stop_loss)
    if four_r is None:
        return None
    side_u = str(side or "").upper()
    extreme = as_float(structure_extreme) if structure_extreme is not None else None
    candidate = four_r
    if extreme is not None and extreme > 0:
        if side_u == "BUY" and extreme > as_float(entry) + PRICE_EPSILON:
            candidate = max(four_r, extreme)
        elif side_u == "SELL" and extreme < as_float(entry) - PRICE_EPSILON:
            candidate = min(four_r, extreme)
    return usable_target(side_u, entry, stop_loss, candidate)


def previous_completed_candle(candles: Sequence[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not candles:
        return None
    ordered = sorted(candles, key=lambda item: item.get("time") or datetime.min)
    # Prefer second-to-last if last may still be forming; for history fetches last is usually complete.
    if len(ordered) >= 2:
        return ordered[-2]
    return ordered[-1]


def structure_extreme_for_side(side: str, candle: Optional[dict[str, Any]]) -> Optional[float]:
    if not candle:
        return None
    if str(side or "").upper() == "SELL":
        return as_float(candle.get("low"))
    return as_float(candle.get("high"))


def serialize_session(doc: dict) -> dict[str, Any]:
    levels = []
    for item in doc.get("levels") or []:
        levels.append(
            {
                "kind": item.get("kind"),
                "price": item.get("price"),
                "status": item.get("status") or "Active",
                "schedule_id": str(item["schedule_id"]) if item.get("schedule_id") else None,
                "structure_extreme": item.get("structure_extreme"),
                "side": item.get("side"),
            }
        )
    highs = [lvl for lvl in levels if lvl.get("kind") == "high"]
    lows = [lvl for lvl in levels if lvl.get("kind") == "low"]
    return {
        "id": str(doc.get("_id")),
        "account_id": str(doc.get("account_id") or "") or None,
        "symbol": doc.get("symbol"),
        "requested_symbol": doc.get("requested_symbol"),
        "display_symbol": doc.get("display_symbol"),
        "structure_timeframe": doc.get("structure_timeframe"),
        "swing_count": doc.get("swing_count"),
        "risk_amount": doc.get("risk_amount"),
        "highs": highs,
        "lows": lows,
        "levels": levels,
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
    }


async def analyze_unmitigated_swings(
    db,
    account: dict,
    *,
    broker_symbol: str,
    requested_symbol: str,
    display: str,
    timeframe: str,
    swing_count: int,
    mid_price: Optional[float],
) -> dict[str, Any]:
    tf = normalize_structure_timeframe(timeframe)
    payload = await get_unmitigated_levels_for_symbol(
        db,
        account,
        broker_symbol,
        tf,
        limit=500,
        swing_length=DEFAULT_SWING_LENGTH,
        atr_adaptive=False,
        use_atr_filter=False,
        use_volume_filter=False,
    )
    highs, lows = slice_highs_and_lows(payload.get("levels") or [], swing_count=swing_count, mid_price=mid_price)
    return {
        "symbol": broker_symbol,
        "requested_symbol": requested_symbol,
        "display_symbol": display,
        "timeframe": tf,
        "swing_count": int(swing_count),
        "bar_count": int(payload.get("bar_count") or 0),
        "mid_price": float(mid_price) if mid_price is not None else None,
        "highs": highs,
        "lows": lows,
    }


async def mark_session_level_mitigated(
    db,
    *,
    structure_session_id: Any,
    structure_price: float,
    structure_kind: Optional[str] = None,
) -> None:
    if not structure_session_id:
        return
    try:
        session_oid = structure_session_id if isinstance(structure_session_id, ObjectId) else ObjectId(str(structure_session_id))
    except Exception:
        return
    doc = await db[SESSION_COLLECTION].find_one_async({"_id": session_oid})
    if not doc:
        return
    price = as_float(structure_price)
    tol = max(1e-6, abs(price) * 1e-8)
    changed = False
    levels = list(doc.get("levels") or [])
    for item in levels:
        if abs(as_float(item.get("price")) - price) > tol:
            continue
        if structure_kind and str(item.get("kind") or "") != str(structure_kind):
            continue
        if str(item.get("status") or "") != "Mitigated":
            item["status"] = "Mitigated"
            changed = True
    if not changed:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db[SESSION_COLLECTION].update_one_async(
        {"_id": session_oid},
        {"$set": {"levels": levels, "updated_at": now}},
    )


async def execute_unmitigated_swings(
    db,
    user: dict,
    account: dict,
    *,
    broker_symbol: str,
    requested_symbol: str,
    display: str,
    structure_timeframe: str,
    highs: Sequence[float],
    lows: Sequence[float],
    risk_amount: float,
    mid_price: float,
    point_size: float,
    price_digits: int,
    seed_candles: list[dict],
) -> dict[str, Any]:
    """Create one-shot M1 schedules and a structure session."""
    from .scheduled_trade_runtime import scheduled_trade_manager

    tf = normalize_structure_timeframe(structure_timeframe)
    structure_candles = await get_recent_chart_candles(
        db, account, broker_symbol, tf, limit=5, min_bars=2, force_broker_refresh=False
    )
    prev = previous_completed_candle(structure_candles)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    session_doc: dict[str, Any] = {
        "user_id": user["_id"],
        "account_id": account["_id"],
        "symbol": broker_symbol,
        "requested_symbol": requested_symbol,
        "display_symbol": display,
        "structure_timeframe": tf,
        "swing_count": len(list(highs)) + len(list(lows)),
        "risk_amount": float(risk_amount),
        "levels": [],
        "created_at": now,
        "updated_at": now,
    }
    insert = await db[SESSION_COLLECTION].insert_one_async(session_doc)
    session_id = insert.inserted_id
    session_doc["_id"] = session_id

    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    levels_out: list[dict[str, Any]] = []

    async def _one(kind: str, price: float) -> None:
        try:
            side = resolve_side_from_level(price, mid_price)
            extreme = structure_extreme_for_side(side, prev)
            schedule = await scheduled_trade_manager.create_schedule(
                db,
                user,
                account,
                symbol=requested_symbol,
                broker_symbol=broker_symbol,
                timeframe="M1",
                level=float(price),
                risk_amount=float(risk_amount),
                target=None,
                retryable_order=False,
                mid_price=float(mid_price),
                point_size=float(point_size),
                price_digits=int(price_digits),
                seed_candles=seed_candles,
                extra_fields={
                    "source": SOURCE_UNMITIGATED_SWINGS,
                    "structure_session_id": session_id,
                    "structure_timeframe": tf,
                    "structure_kind": kind,
                    "structure_price": float(price),
                    "structure_extreme": float(extreme) if extreme is not None else None,
                },
            )
            levels_out.append(
                {
                    "kind": kind,
                    "price": float(price),
                    "status": "Active",
                    "schedule_id": schedule.get("id"),
                    "structure_extreme": float(extreme) if extreme is not None else None,
                    "side": side,
                }
            )
            created.append(schedule)
        except Exception as exc:
            errors.append({"kind": kind, "price": float(price), "detail": str(exc)})
            levels_out.append(
                {
                    "kind": kind,
                    "price": float(price),
                    "status": "Active",
                    "schedule_id": None,
                    "structure_extreme": None,
                    "side": None,
                    "error": str(exc),
                }
            )

    for price in highs:
        await _one("high", float(price))
    for price in lows:
        await _one("low", float(price))

    await db[SESSION_COLLECTION].update_one_async(
        {"_id": session_id},
        {"$set": {"levels": levels_out, "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)}},
    )
    session_doc["levels"] = levels_out
    return {
        "session": serialize_session(session_doc),
        "created": created,
        "errors": errors,
    }


async def get_structure_session(db, user_id: ObjectId, session_id: ObjectId) -> Optional[dict]:
    doc = await db[SESSION_COLLECTION].find_one_async({"_id": session_id, "user_id": user_id})
    if not doc:
        return None
    return serialize_session(doc)
