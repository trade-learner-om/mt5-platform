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
MERGE_PCT = 0.01
LOOKBACK_START = 500
LOOKBACK_MAX = 5000


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


def _within_pct(a: float, b: float, pct: float = MERGE_PCT) -> bool:
    base = max(abs(a), abs(b), PRICE_EPSILON)
    return abs(a - b) / base <= pct + PRICE_EPSILON


def merge_levels_within_pct(
    levels: Sequence[dict[str, Any]],
    *,
    pct: float = MERGE_PCT,
) -> list[dict[str, Any]]:
    """Cluster same-kind levels within ``pct``; keep extreme price per cluster."""
    highs = [item for item in levels if item.get("kind") == "high" and not item.get("mitigated")]
    lows = [item for item in levels if item.get("kind") == "low" and not item.get("mitigated")]

    def _merge(side_levels: list[dict[str, Any]], *, prefer_high: bool) -> list[dict[str, Any]]:
        remaining = sorted(side_levels, key=lambda item: as_float(item.get("price")), reverse=prefer_high)
        merged: list[dict[str, Any]] = []
        while remaining:
            seed = remaining.pop(0)
            seed_price = as_float(seed.get("price"))
            cluster = [seed]
            kept: list[dict[str, Any]] = []
            for candidate in remaining:
                if _within_pct(seed_price, as_float(candidate.get("price")), pct):
                    cluster.append(candidate)
                else:
                    kept.append(candidate)
            remaining = kept
            if prefer_high:
                best = max(cluster, key=lambda item: as_float(item.get("price")))
            else:
                best = min(cluster, key=lambda item: as_float(item.get("price")))
            merged.append(best)
        return merged

    return _merge(highs, prefer_high=True) + _merge(lows, prefer_high=False)


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


def _lookback_limits() -> list[int]:
    limits: list[int] = []
    current = LOOKBACK_START
    while current <= LOOKBACK_MAX:
        limits.append(current)
        if current >= LOOKBACK_MAX:
            break
        current = min(LOOKBACK_MAX, current * 2)
    return limits


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


def serialize_session(doc: dict, *, schedules_by_id: Optional[dict[str, dict]] = None) -> dict[str, Any]:
    schedules_by_id = schedules_by_id or {}
    levels = []
    for item in doc.get("levels") or []:
        schedule_id = str(item["schedule_id"]) if item.get("schedule_id") else None
        schedule = schedules_by_id.get(schedule_id or "") if schedule_id else None
        level_status = item.get("status") or "Active"
        trade_status = None
        entry = None
        stop_loss = None
        quantity = None
        order_id = None
        last_error = None
        placed_at = None
        filled_at = None
        exited_at = None
        target = None
        if schedule:
            trade_status = schedule.get("status")
            entry = schedule.get("entry")
            stop_loss = schedule.get("stop_loss")
            quantity = schedule.get("quantity")
            order_id = str(schedule["order_id"]) if schedule.get("order_id") else None
            last_error = schedule.get("last_error")
            placed_at = _iso(schedule.get("placed_at"))
            filled_at = _iso(schedule.get("filled_at"))
            exited_at = _iso(schedule.get("exited_at"))
            target = schedule.get("target")
            # Prefer schedule side if present
            side = schedule.get("side") or item.get("side")
        else:
            side = item.get("side")
        levels.append(
            {
                "kind": item.get("kind"),
                "price": item.get("price"),
                "status": level_status,
                "schedule_id": schedule_id,
                "structure_extreme": item.get("structure_extreme"),
                "side": side,
                "trade_status": trade_status,
                "entry": entry,
                "stop_loss": stop_loss,
                "target": target,
                "quantity": quantity,
                "order_id": order_id,
                "last_error": last_error,
                "placed_at": placed_at,
                "filled_at": filled_at,
                "exited_at": exited_at,
                "error": item.get("error"),
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
        "status": doc.get("status") or "active",
        "highs": highs,
        "lows": lows,
        "levels": levels,
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
    }


async def _load_schedules_by_id(db, schedule_ids: Sequence[Any]) -> dict[str, dict]:
    oids: list[ObjectId] = []
    for value in schedule_ids:
        if not value:
            continue
        try:
            oids.append(value if isinstance(value, ObjectId) else ObjectId(str(value)))
        except Exception:
            continue
    if not oids:
        return {}
    docs = await db["scheduled_trades"].find_async({"_id": {"$in": oids}})
    return {str(doc.get("_id")): doc for doc in docs}


async def serialize_session_enriched(db, doc: dict) -> dict[str, Any]:
    schedule_ids = [item.get("schedule_id") for item in (doc.get("levels") or [])]
    schedules = await _load_schedules_by_id(db, schedule_ids)
    return serialize_session(doc, schedules_by_id=schedules)


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
    count = max(1, min(int(swing_count), 50))
    payload: dict[str, Any] = {"levels": [], "bar_count": 0}
    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    lookback_exhausted = False

    for limit in _lookback_limits():
        payload = await get_unmitigated_levels_for_symbol(
            db,
            account,
            broker_symbol,
            tf,
            limit=limit,
            swing_length=DEFAULT_SWING_LENGTH,
            atr_adaptive=False,
            use_atr_filter=False,
            use_volume_filter=False,
        )
        merged = merge_levels_within_pct(payload.get("levels") or [], pct=MERGE_PCT)
        highs, lows = slice_highs_and_lows(merged, swing_count=count, mid_price=mid_price)
        bar_count = int(payload.get("bar_count") or 0)
        if len(highs) >= count and len(lows) >= count:
            lookback_exhausted = False
            break
        if bar_count < limit or limit >= LOOKBACK_MAX:
            lookback_exhausted = True
            break

    short_highs = len(highs) < count
    short_lows = len(lows) < count
    lookback_exhausted = bool(lookback_exhausted or short_highs or short_lows)

    return {
        "symbol": broker_symbol,
        "requested_symbol": requested_symbol,
        "display_symbol": display,
        "timeframe": tf,
        "swing_count": int(count),
        "bar_count": int(payload.get("bar_count") or 0),
        "lookback_exhausted": lookback_exhausted,
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
            item["mitigated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            changed = True
    if not changed:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db[SESSION_COLLECTION].update_one_async(
        {"_id": session_oid},
        {"$set": {"levels": levels, "updated_at": now}},
    )


def _level_matches_schedule(item: dict, schedule: dict) -> bool:
    schedule_id = item.get("schedule_id")
    if schedule_id and str(schedule_id) == str(schedule.get("_id")):
        return True
    price = as_float(item.get("price"))
    structure_price = as_float(schedule.get("structure_price") or schedule.get("level"))
    tol = max(1e-6, abs(structure_price) * 1e-8)
    if abs(price - structure_price) > tol:
        return False
    kind = schedule.get("structure_kind")
    if kind and str(item.get("kind") or "") != str(kind):
        return False
    return True


async def persist_schedule_progress_to_session(db, schedule: dict) -> None:
    """Mirror schedule/trade lifecycle onto the owning structure session level in MongoDB."""
    if str(schedule.get("source") or "") != SOURCE_UNMITIGATED_SWINGS:
        return
    session_id = schedule.get("structure_session_id")
    if not session_id:
        return
    try:
        session_oid = session_id if isinstance(session_id, ObjectId) else ObjectId(str(session_id))
    except Exception:
        return
    doc = await db[SESSION_COLLECTION].find_one_async({"_id": session_oid})
    if not doc:
        return
    levels = list(doc.get("levels") or [])
    changed = False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    trade_status = str(schedule.get("status") or "")
    for item in levels:
        if not _level_matches_schedule(item, schedule):
            continue
        if not item.get("schedule_id"):
            item["schedule_id"] = schedule.get("_id")
        item["side"] = schedule.get("side") or item.get("side")
        item["trade_status"] = trade_status
        item["entry"] = schedule.get("entry")
        item["stop_loss"] = schedule.get("stop_loss")
        item["target"] = schedule.get("target")
        item["quantity"] = schedule.get("quantity")
        item["order_id"] = schedule.get("order_id")
        item["meta_order_id"] = schedule.get("meta_order_id")
        item["last_error"] = schedule.get("last_error")
        item["armed_at"] = schedule.get("armed_at")
        item["placed_at"] = schedule.get("placed_at")
        item["filled_at"] = schedule.get("filled_at")
        item["exited_at"] = schedule.get("exited_at")
        item["progress_updated_at"] = now
        if trade_status == "ARMED" and str(item.get("status") or "") != "Mitigated":
            item["status"] = "Mitigated"
            item["mitigated_at"] = now
        changed = True
    if not changed:
        return

    terminal = {
        "TARGET_EXIT",
        "STOP_EXIT",
        "USER_EXIT",
        "CANCELLED",
        "RETRY_TARGET_EXIT",
        "RETRY_STOP_EXIT",
        "RETRY_USER_EXIT",
        "RETRY_CANCELLED",
    }
    all_done = True
    for item in levels:
        if item.get("error") and not item.get("schedule_id"):
            continue
        trade_status = str(item.get("trade_status") or "")
        if not item.get("schedule_id"):
            all_done = False
            break
        if trade_status not in terminal:
            all_done = False
            break

    session_status = "completed" if all_done else "active"
    await db[SESSION_COLLECTION].update_one_async(
        {"_id": session_oid},
        {"$set": {"levels": levels, "updated_at": now, "status": session_status}},
    )


async def list_structure_sessions(
    db,
    user_id: ObjectId,
    *,
    account_id: Optional[ObjectId] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"user_id": user_id}
    if account_id is not None:
        query["account_id"] = account_id
    docs = await db[SESSION_COLLECTION].find_async(query)
    docs.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or datetime.min, reverse=True)
    docs = docs[: max(1, min(int(limit), 50))]
    out: list[dict[str, Any]] = []
    for doc in docs:
        out.append(await serialize_session_enriched(db, doc))
    return out


async def get_active_structure_session(
    db,
    user_id: ObjectId,
    account_id: ObjectId,
) -> Optional[dict[str, Any]]:
    docs = await db[SESSION_COLLECTION].find_async(
        {
            "user_id": user_id,
            "account_id": account_id,
            "status": {"$ne": "completed"},
        }
    )
    if not docs:
        # Fall back to most recently updated session for the account.
        docs = await db[SESSION_COLLECTION].find_async({"user_id": user_id, "account_id": account_id})
    if not docs:
        return None
    docs.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or datetime.min, reverse=True)
    return await serialize_session_enriched(db, docs[0])


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
        "status": "active",
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
                    "trade_status": schedule.get("status") or "INITIATED",
                    "entry": schedule.get("entry"),
                    "stop_loss": schedule.get("stop_loss"),
                    "target": schedule.get("target"),
                    "quantity": schedule.get("quantity"),
                    "order_id": schedule.get("order_id"),
                    "last_error": schedule.get("last_error"),
                    "progress_updated_at": now,
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
                    "trade_status": None,
                    "error": str(exc),
                    "progress_updated_at": now,
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
        "session": await serialize_session_enriched(db, session_doc),
        "created": created,
        "errors": errors,
    }


async def get_structure_session(db, user_id: ObjectId, session_id: ObjectId) -> Optional[dict]:
    doc = await db[SESSION_COLLECTION].find_one_async({"_id": session_id, "user_id": user_id})
    if not doc:
        return None
    return await serialize_session_enriched(db, doc)
