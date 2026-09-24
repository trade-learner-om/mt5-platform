from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional, Sequence

from pymongo import UpdateOne

from .analytics.market_structure import (
    DEFAULT_SWING_LENGTH,
    calculate_unmitigated_levels,
    candles_to_ohlcv_frame,
    supports_and_resistances_from_levels,
)
from .metaapi_client import metaapi_service

logger = logging.getLogger(__name__)

CANDLE_COLLECTION = "candles"
MARKET_INTERNATIONAL = "INTERNATIONAL"
BROKER_MT5 = "MT5"

TIMEFRAME_ALIASES = {
    "1m": "M1",
    "m1": "M1",
    "5m": "M5",
    "m5": "M5",
    "15m": "M15",
    "m15": "M15",
    "45m": "M45",
    "m45": "M45",
    "1h": "H1",
    "h1": "H1",
    "4h": "H4",
    "h4": "H4",
    "6h": "H6",
    "h6": "H6",
    "12h": "H12",
    "h12": "H12",
    "d": "D1",
    "1d": "D1",
    "d1": "D1",
}

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M45": 2700,
    "H1": 3600,
    "H4": 14400,
    "H6": 21600,
    "H12": 43200,
    "D1": 86400,
}

# Native MT5 timeframes only. H6/H12 are aggregated from H1; M45 from M15.
METAAPI_TIMEFRAME_BY_NORMALIZED = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}

AGGREGATED_FROM: dict[str, tuple[str, int]] = {
    "M45": ("M15", 3),
    "H6": ("H1", 6),
    "H12": ("H1", 12),
}

BACKTEST_MAX_BARS_BY_TIMEFRAME = {
    "M1": 20000,
    "M5": 20000,
    "M15": 20000,
    "H1": 5000,
    "H4": 5000,
    "H6": 5000,
    "H12": 5000,
    "D1": 5000,
}


def normalize_timeframe(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in TIMEFRAME_ALIASES:
        raise ValueError("Unsupported timeframe")
    return TIMEFRAME_ALIASES[normalized]


def timeframe_seconds(timeframe: str) -> int:
    return TIMEFRAME_SECONDS[normalize_timeframe(timeframe)]


def parse_chart_datetime(value, default: Optional[datetime] = None) -> datetime:
    if value in (None, ""):
        if default is None:
            raise ValueError("Missing datetime")
        return default
    text = str(value).strip()
    try:
        if text.isdigit():
            timestamp = int(text)
            if timestamp > 10_000_000_000:
                timestamp = timestamp // 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception as exc:
        raise ValueError("Invalid datetime") from exc


def _utc_naive(value: datetime) -> datetime:
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).replace(tzinfo=None)


def candle_scope(account: dict, symbol: str, timeframe: str) -> dict:
    return {
        "broker": BROKER_MT5,
        "broker_account_id": str(account.get("account_id") or ""),
        "market": MARKET_INTERNATIONAL,
        "symbol": str(symbol or "").upper(),
        "timeframe": normalize_timeframe(timeframe),
    }


def _normalize_source_candle(candle: dict) -> dict:
    candle_time = candle.get("time")
    if isinstance(candle_time, datetime):
        time_value = candle_time if candle_time.tzinfo else candle_time.replace(tzinfo=timezone.utc)
    else:
        time_value = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00"))
    return {
        "time": _utc_naive(time_value),
        "open": float(candle.get("open") or 0),
        "high": float(candle.get("high") or 0),
        "low": float(candle.get("low") or 0),
        "close": float(candle.get("close") or 0),
        "volume": int(candle.get("volume") or candle.get("tickVolume") or candle.get("tick_count") or 0),
        "source": str(candle.get("source") or "MT5"),
    }


def upsert_candles(db, account: dict, symbol: str, timeframe: str, candles: list[dict]):
    scope = candle_scope(account, symbol, timeframe)
    now = datetime.utcnow()
    operations = []
    for candle in candles:
        normalized = _normalize_source_candle(candle)
        operations.append(
            UpdateOne(
                {**scope, "time": normalized["time"]},
                {
                    "$set": {
                        **scope,
                        "time": normalized["time"],
                        "open": normalized["open"],
                        "high": normalized["high"],
                        "low": normalized["low"],
                        "close": normalized["close"],
                        "volume": normalized["volume"],
                        "source": normalized["source"],
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        )
    if operations:
        db[CANDLE_COLLECTION].bulk_write(operations, ordered=False)


def load_cached_candles(db, account: dict, symbol: str, timeframe: str, from_time: datetime, to_time: datetime, limit: int) -> list[dict]:
    query = {
        **candle_scope(account, symbol, timeframe),
        "time": {"$gte": _utc_naive(from_time), "$lte": _utc_naive(to_time)},
    }
    return list(db[CANDLE_COLLECTION].find(query).sort("time", 1).limit(limit))


def _has_coverage(docs: list[dict], from_time: datetime, to_time: datetime, seconds: int) -> bool:
    if not docs:
        return False
    first_time = docs[0].get("time")
    last_time = docs[-1].get("time")
    if first_time is None or last_time is None:
        return False
    from_naive = _utc_naive(from_time)
    to_naive = _utc_naive(to_time)
    if first_time > from_naive + timedelta(seconds=seconds):
        return False
    if last_time < to_naive - timedelta(seconds=seconds):
        return False
    expected_max_gap = seconds * 1.5
    for left, right in zip(docs, docs[1:]):
        left_time = left.get("time")
        right_time = right.get("time")
        if left_time and right_time and (right_time - left_time).total_seconds() > expected_max_gap:
            return False
    return True


def serialize_chart_candle(doc: dict) -> dict:
    time_value = doc.get("time")
    if isinstance(time_value, datetime):
        normalized = time_value if time_value.tzinfo else time_value.replace(tzinfo=timezone.utc)
        timestamp = int(normalized.astimezone(timezone.utc).timestamp())
    else:
        timestamp = int(datetime.fromisoformat(str(time_value).replace("Z", "+00:00")).timestamp())
    return {
        "time": timestamp,
        "open": float(doc.get("open") or 0),
        "high": float(doc.get("high") or 0),
        "low": float(doc.get("low") or 0),
        "close": float(doc.get("close") or 0),
        "volume": int(doc.get("volume") or 0),
    }


def delete_cached_candles(
    db,
    account: dict,
    symbol: str,
    timeframe: str,
    from_time: datetime,
    to_time: datetime,
) -> int:
    """Remove cached bars in [from, to] so re-aggregation can replace stale opens."""
    query = {
        **candle_scope(account, symbol, timeframe),
        "time": {"$gte": _utc_naive(from_time), "$lte": _utc_naive(to_time)},
    }
    result = db[CANDLE_COLLECTION].delete_many(query)
    return int(getattr(result, "deleted_count", 0) or 0)


def _format_sample_times(candles: list[dict], *, limit: int = 6) -> str:
    samples = []
    for candle in candles[:limit]:
        time_value = candle.get("time")
        if isinstance(time_value, datetime):
            samples.append(time_value.isoformat())
        elif isinstance(time_value, (int, float)):
            samples.append(datetime.fromtimestamp(int(time_value), tz=timezone.utc).isoformat())
        else:
            samples.append(str(time_value))
    if len(candles) > limit:
        samples.append(f"...(+{len(candles) - limit})")
    return "[" + ", ".join(samples) + "]"


def _candle_epoch_seconds(candle: dict) -> int:
    time_value = candle["time"]
    if isinstance(time_value, datetime):
        aware = time_value if time_value.tzinfo else time_value.replace(tzinfo=timezone.utc)
        return int(aware.timestamp())
    if isinstance(time_value, (int, float)):
        ts = float(time_value)
        if ts > 1e12:
            ts /= 1000.0
        return int(ts)
    text = str(time_value).strip()
    if text.isdigit():
        ts = float(text)
        if ts > 1e12:
            ts /= 1000.0
        return int(ts)
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def _infer_bar_phase(candles: list[dict], base_seconds: int, *, majority: float = 0.7) -> int:
    """Infer open-time phase within `base_seconds` (e.g. 1800 for H1 xx:30 brokers)."""
    if base_seconds <= 0 or not candles:
        return 0
    counts: dict[int, int] = {}
    for candle in candles:
        phase = _candle_epoch_seconds(candle) % base_seconds
        counts[phase] = counts.get(phase, 0) + 1
    mode_phase, mode_count = max(counts.items(), key=lambda item: item[1])
    ratio = mode_count / len(candles)
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    logger.info(
        "candle phase infer base=%ss bars=%s mode=%ss (%.0f%%) top=%s sample=%s",
        base_seconds,
        len(candles),
        mode_phase,
        ratio * 100,
        top,
        _format_sample_times(candles),
    )
    if ratio < majority:
        logger.info(
            "Unstable candle phase for base=%ss (mode=%ss on %s/%s bars); falling back to 0",
            base_seconds,
            mode_phase,
            mode_count,
            len(candles),
        )
        return 0
    return int(mode_phase)


def _aggregate_candles(candles: list[dict], timeframe: str) -> list[dict]:
    """Aggregate source bars into a synthetic TF, preserving broker open phase.

    H6/H12 from H1 (and M45 from M15) use bucket =
    ((ts - phase) // period) * period + phase
    where phase is inferred from source bar opens (0 for xx:00, 1800 for xx:30).
    """
    normalized_tf = normalize_timeframe(timeframe)
    target_seconds = TIMEFRAME_SECONDS[normalized_tf]
    source_tf = AGGREGATED_FROM.get(normalized_tf, (None, 1))[0]
    base_seconds = TIMEFRAME_SECONDS.get(source_tf or normalized_tf, target_seconds)
    sorted_candles = sorted((_normalize_source_candle(item) for item in candles), key=lambda item: item["time"])
    phase = _infer_bar_phase(sorted_candles, base_seconds)
    buckets = {}
    for candle in sorted_candles:
        timestamp = _candle_epoch_seconds(candle)
        aligned = ((timestamp - phase) // target_seconds) * target_seconds + phase
        bucket_start = datetime.fromtimestamp(aligned, tz=timezone.utc).replace(tzinfo=None)
        current = buckets.get(bucket_start)
        if current is None:
            buckets[bucket_start] = {
                "time": bucket_start,
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle["volume"],
                "source": "MT5",
            }
            continue
        current["high"] = max(current["high"], candle["high"])
        current["low"] = min(current["low"], candle["low"])
        current["close"] = candle["close"]
        current["volume"] += candle["volume"]
    aggregated = [buckets[key] for key in sorted(buckets)]
    logger.info(
        "aggregate %s from %s: source=%s phase=%ss period=%ss out=%s opens=%s",
        normalized_tf,
        source_tf or normalized_tf,
        len(sorted_candles),
        phase,
        target_seconds,
        len(aggregated),
        _format_sample_times(aggregated),
    )
    return aggregated


def _source_fetch_spec(timeframe: str) -> tuple[str, str, int]:
    """Return (normalized_target, native_metaapi_tf_or_normalized, multiplier)."""
    normalized = normalize_timeframe(timeframe)
    if normalized in AGGREGATED_FROM:
        source_tf, multiplier = AGGREGATED_FROM[normalized]
        return normalized, METAAPI_TIMEFRAME_BY_NORMALIZED[source_tf], multiplier
    meta = METAAPI_TIMEFRAME_BY_NORMALIZED.get(normalized)
    if not meta:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return normalized, meta, 1


async def _fetch_mt5_candles_from(account: dict, symbol: str, timeframe: str, from_time: datetime, limit: int) -> list[dict]:
    normalized, source_tf, multiplier = _source_fetch_spec(timeframe)
    fetch_limit = min(max(int(limit or 1) * multiplier + multiplier, limit), 20000) if multiplier > 1 else limit
    source = await metaapi_service.get_historical_candles(
        account["api_token"],
        account["account_id"],
        symbol,
        source_tf,
        start_time=from_time,
        limit=fetch_limit,
    )
    if multiplier == 1:
        return source
    return _aggregate_candles(source, normalized)


def _log_source_time_faces(source: list[dict], *, limit: int = 3) -> None:
    """Log UTC vs IST faces so Local/IST chart confusion is obvious (no behavior change)."""
    ist = timezone(timedelta(hours=5, minutes=30))
    faces = []
    for item in (source or [])[:limit]:
        try:
            epoch = _candle_epoch_seconds({"time": item.get("time")})
        except Exception:
            continue
        as_utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
        as_ist = as_utc.astimezone(ist)
        faces.append(f"epoch={epoch} utc={as_utc.isoformat()} ist={as_ist.isoformat()}")
    if faces:
        logger.info("source candle time faces (UTC label vs IST display): %s", "; ".join(faces))


async def _fetch_mt5_candles_range(
    account: dict,
    symbol: str,
    timeframe: str,
    from_time: datetime,
    to_time: datetime,
) -> list[dict]:
    """Fetch [from, to] via copy_rates_range on the native source TF, then aggregate if needed.

    Used for synthetic TFs (H6/H12 from H1, M45 from M15). Do not use copy_rates_from
    here — that walks backward from from_time and leaves the in-range cache empty.
    """
    normalized, source_tf, multiplier = _source_fetch_spec(timeframe)
    source = await metaapi_service.get_historical_candles_range(
        account["api_token"],
        account["account_id"],
        symbol,
        source_tf,
        from_time,
        to_time,
    )
    if multiplier == 1:
        return source
    logger.info(
        "range-fetch %s→%s symbol=%s source_bars=%s sample=%s from=%s to=%s",
        source_tf,
        normalized,
        symbol,
        len(source or []),
        _format_sample_times([{"time": item.get("time")} for item in (source or [])], limit=8),
        _utc_naive(from_time).isoformat(),
        _utc_naive(to_time).isoformat(),
    )
    _log_source_time_faces(source or [])
    return _aggregate_candles(source, normalized)


async def _fetch_mt5_candles(account: dict, symbol: str, timeframe: str, to_time: datetime, limit: int) -> list[dict]:
    # Aggregate synthetic TFs (M45 from M15; H6/H12 from H1) — MT5 has no native H6/H12.
    normalized, source_tf, multiplier = _source_fetch_spec(timeframe)
    fetch_limit = min(max(int(limit or 1) * multiplier + multiplier, limit), 20000) if multiplier > 1 else limit
    source = await metaapi_service.get_historical_candles(
        account["api_token"],
        account["account_id"],
        symbol,
        source_tf,
        start_time=to_time,
        limit=fetch_limit,
    )
    if multiplier == 1:
        return source
    return _aggregate_candles(source, normalized)


async def get_chart_candles(db, account: dict, symbol: str, timeframe: str, from_time: datetime, to_time: datetime, limit: int) -> list[dict]:
    normalized_timeframe = normalize_timeframe(timeframe)
    seconds = TIMEFRAME_SECONDS[normalized_timeframe]
    max_bars = max(1, min(int(limit or 300), 5000))
    cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
    now_utc = datetime.now(timezone.utc)
    refresh_recent = _utc_naive(to_time) >= _utc_naive(now_utc) - timedelta(seconds=seconds * 2)
    if refresh_recent or not _has_coverage(cached, from_time, to_time, seconds):
        span_bars = int(max(1, (to_time - from_time).total_seconds() // seconds)) + 10
        fetch_limit = min(max(max_bars, span_bars), 5000)
        fetched = await _fetch_mt5_candles(account, symbol, normalized_timeframe, to_time, fetch_limit)
        normalized_fetched = [_normalize_source_candle(item) for item in fetched]
        filtered = [
            candle for candle in normalized_fetched
            if _utc_naive(from_time) <= candle["time"] <= _utc_naive(to_time)
        ]
        upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
        if not filtered and not cached and normalized_fetched:
            # If the workstation clock is ahead of the broker's latest candle,
            # the requested range can be in the future. Return the broker's
            # latest candles instead of rendering an empty chart.
            latest = sorted(normalized_fetched, key=lambda item: item["time"])[-max_bars:]
            return [serialize_chart_candle(candle) for candle in latest]
        cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
    return [serialize_chart_candle(doc) for doc in cached]


async def get_fresh_candles(
    db,
    account: dict,
    symbol: str,
    *,
    timeframe: str = "H4",
    limit: int = 20,
) -> list[dict]:
    """Pull candles from MT5 via copy_rates_from_pos (forming bar is last).

    H6/H12 are synthesized from H1; M45 from M15.
    """
    normalized_timeframe = normalize_timeframe(timeframe)
    _target, source_tf, multiplier = _source_fetch_spec(normalized_timeframe)
    fetch_limit = max(int(limit or 20) + 2, 20)
    if multiplier > 1:
        fetch_limit = min(max(fetch_limit * multiplier + multiplier, fetch_limit), 20000)
    fetched = await metaapi_service.get_historical_candles(
        account["api_token"],
        account["account_id"],
        symbol,
        source_tf,
        limit=fetch_limit,
    )
    if not fetched:
        raise RuntimeError(f"MT5 returned no {normalized_timeframe} candles")
    if multiplier > 1:
        fetched = _aggregate_candles(fetched, normalized_timeframe)
    normalized_fetched = [_normalize_source_candle(item) for item in fetched]
    upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
    latest = sorted(normalized_fetched, key=lambda item: item["time"])[-fetch_limit:]
    candles = [serialize_chart_candle(candle) for candle in latest]
    _warn_large_candle_gaps(candles, max_gap_seconds=TIMEFRAME_SECONDS[normalized_timeframe] * 1.5)
    return candles


async def get_fresh_h4_candles(
    db,
    account: dict,
    symbol: str,
    *,
    limit: int = 20,
) -> list[dict]:
    return await get_fresh_candles(db, account, symbol, timeframe="H4", limit=limit)


async def get_recent_chart_candles(
    db,
    account: dict,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 12,
    min_bars: int = 2,
    force_broker_refresh: bool = False,
) -> list[dict]:
    """Load recent chart candles, falling back to a direct MT5 fetch when cache/range is sparse."""
    normalized_timeframe = normalize_timeframe(timeframe)
    seconds = TIMEFRAME_SECONDS[normalized_timeframe]
    max_bars = max(min_bars, int(limit or min_bars))
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(seconds=seconds * max_bars)

    if force_broker_refresh:
        fetch_limit = max(min_bars + 2, max_bars)
        fetched = await _fetch_mt5_candles(account, symbol, timeframe, to_time, fetch_limit)
        if fetched:
            normalized_fetched = [_normalize_source_candle(item) for item in fetched]
            upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
            latest = sorted(normalized_fetched, key=lambda item: item["time"])[-fetch_limit:]
            return [serialize_chart_candle(candle) for candle in latest]

    candles = await get_chart_candles(db, account, symbol, timeframe, from_time, to_time, max_bars)
    if len(candles) >= min_bars:
        return candles

    fetch_limit = max(min_bars + 2, max_bars)
    fetched = await _fetch_mt5_candles(account, symbol, timeframe, to_time, fetch_limit)
    if not fetched:
        return candles

    normalized_fetched = [_normalize_source_candle(item) for item in fetched]
    upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
    latest = sorted(normalized_fetched, key=lambda item: item["time"])[-fetch_limit:]
    return [serialize_chart_candle(candle) for candle in latest]


def _warn_large_candle_gaps(candles: list[dict], *, max_gap_seconds: float = 14400 * 1.5) -> None:
    if len(candles) < 2:
        return
    for left, right in zip(candles, candles[1:]):
        left_time = left.get("time")
        right_time = right.get("time")
        if left_time is None or right_time is None:
            continue
        if isinstance(left_time, (int, float)):
            left_dt = datetime.fromtimestamp(int(left_time), tz=timezone.utc)
            right_dt = datetime.fromtimestamp(int(right_time), tz=timezone.utc)
        else:
            left_dt = left_time if isinstance(left_time, datetime) else datetime.fromisoformat(str(left_time))
            right_dt = right_time if isinstance(right_time, datetime) else datetime.fromisoformat(str(right_time))
        gap_seconds = (right_dt - left_dt).total_seconds()
        if gap_seconds > max_gap_seconds:
            logger.info(
                "candle gap %.1f hours between %s and %s (expected over weekends)",
                gap_seconds / 3600,
                left_dt.isoformat(),
                right_dt.isoformat(),
            )


def _warn_large_h4_gaps(candles: list[dict], *, max_gap_seconds: float = 14400 * 1.5) -> None:
    _warn_large_candle_gaps(candles, max_gap_seconds=max_gap_seconds)


async def get_backtest_candles(
    db,
    account: dict,
    symbol: str,
    from_time: datetime,
    to_time: datetime,
    *,
    timeframe: str = "H4",
) -> list[dict]:
    """Load contiguous candles for backtest by fetching forward from range start."""
    normalized_timeframe = normalize_timeframe(timeframe)
    seconds = TIMEFRAME_SECONDS[normalized_timeframe]
    span_bars = int(max(1, (to_time - from_time).total_seconds() // seconds)) + 16
    max_bars_cap = BACKTEST_MAX_BARS_BY_TIMEFRAME.get(normalized_timeframe, 5000)
    max_bars = min(max(span_bars, 12), max_bars_cap)
    cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
    has_coverage = _has_coverage(cached, from_time, to_time, seconds)
    account_id = str(account.get("account_id") or "")
    logger.info(
        "backtest candles %s %s %s..%s cached=%s coverage=%s sample=%s",
        symbol,
        normalized_timeframe,
        _utc_naive(from_time).isoformat(),
        _utc_naive(to_time).isoformat(),
        len(cached),
        has_coverage,
        _format_sample_times(cached),
    )

    # Synthetic TFs (H6/H12/M45) may have stale cache from prior aggregation.
    # Always re-fetch source + re-aggregate, then replace the in-range cache.
    force_refresh_aggregated = normalized_timeframe in AGGREGATED_FROM
    if force_refresh_aggregated or not has_coverage:
        if force_refresh_aggregated and has_coverage:
            source_tf = AGGREGATED_FROM[normalized_timeframe][0]
            base_seconds = TIMEFRAME_SECONDS[source_tf]
            cached_phase = _infer_bar_phase(cached, base_seconds) if cached else None
            logger.info(
                "backtest candles %s %s forcing aggregated refresh (cached_phase=%ss)",
                symbol,
                normalized_timeframe,
                cached_phase,
            )
        if normalized_timeframe in AGGREGATED_FROM:
            fetched = await _fetch_mt5_candles_range(
                account, symbol, normalized_timeframe, from_time, to_time
            )
        else:
            metaapi_timeframe = METAAPI_TIMEFRAME_BY_NORMALIZED.get(normalized_timeframe, "4h")
            try:
                fetched = await metaapi_service.get_historical_candles_range(
                    account["api_token"],
                    account["account_id"],
                    symbol,
                    metaapi_timeframe,
                    from_time,
                    to_time,
                )
            except Exception:
                fetched = await _fetch_mt5_candles_from(account, symbol, normalized_timeframe, from_time, max_bars)
        normalized_fetched = [_normalize_source_candle(item) for item in fetched]
        if normalized_timeframe in AGGREGATED_FROM:
            deleted = delete_cached_candles(
                db, account, symbol, normalized_timeframe, from_time, to_time
            )
            logger.info(
                "backtest candles %s %s deleted stale cache rows=%s account=%s",
                symbol,
                normalized_timeframe,
                deleted,
                account_id,
            )
        upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
        cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
        logger.info(
            "backtest candles %s %s after refresh count=%s sample=%s",
            symbol,
            normalized_timeframe,
            len(cached),
            _format_sample_times(cached),
        )
    else:
        logger.info(
            "backtest candles %s %s using cache account=%s",
            symbol,
            normalized_timeframe,
            account_id,
        )
    candles = [serialize_chart_candle(doc) for doc in cached]
    _warn_large_candle_gaps(candles, max_gap_seconds=seconds * 1.5)
    return candles


async def get_backtest_h4_candles(
    db,
    account: dict,
    symbol: str,
    from_time: datetime,
    to_time: datetime,
) -> list[dict]:
    """Load contiguous H4 candles for backtest by fetching forward from range start."""
    return await get_backtest_candles(
        db,
        account,
        symbol,
        from_time,
        to_time,
        timeframe="H4",
    )


async def get_backtest_m5_candles(
    db,
    account: dict,
    symbol: str,
    from_time: datetime,
    to_time: datetime,
) -> list[dict]:
    """Load contiguous M5 candles for Trap Hunter backtest."""
    normalized_timeframe = "M5"
    seconds = TIMEFRAME_SECONDS[normalized_timeframe]
    span_bars = int(max(1, (to_time - from_time).total_seconds() // seconds)) + 32
    max_bars = min(max(span_bars, 48), 20000)
    cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
    if not _has_coverage(cached, from_time, to_time, seconds):
        try:
            fetched = await metaapi_service.get_historical_candles_range(
                account["api_token"],
                account["account_id"],
                symbol,
                "5m",
                from_time,
                to_time,
            )
        except Exception:
            fetched = await _fetch_mt5_candles_from(account, symbol, normalized_timeframe, from_time, max_bars)
        normalized_fetched = [_normalize_source_candle(item) for item in fetched]
        upsert_candles(db, account, symbol, normalized_timeframe, normalized_fetched)
        cached = load_cached_candles(db, account, symbol, normalized_timeframe, from_time, to_time, max_bars)
    return [serialize_chart_candle(doc) for doc in cached]


def unmitigated_levels_for_candles(
    candles: Sequence[dict[str, Any]],
    *,
    swing_length: int = DEFAULT_SWING_LENGTH,
    atr_adaptive: bool = False,
    use_atr_filter: bool = False,
    use_volume_filter: bool = False,
    mitigate_on: str = "wick",
    include_mitigated: bool = False,
) -> list[dict[str, Any]]:
    """Compute active unmitigated swing highs/lows for a candle list (any timeframe)."""
    frame = candles_to_ohlcv_frame(list(candles))
    return calculate_unmitigated_levels(
        frame,
        swing_length=int(swing_length),
        atr_adaptive=bool(atr_adaptive),
        use_atr_filter=bool(use_atr_filter),
        use_volume_filter=bool(use_volume_filter),
        mitigate_on=mitigate_on,  # type: ignore[arg-type]
        include_mitigated=bool(include_mitigated),
    )


def unmitigated_supports_resistances_for_candles(
    candles: Sequence[dict[str, Any]],
    *,
    swing_length: int = DEFAULT_SWING_LENGTH,
    atr_adaptive: bool = False,
    use_atr_filter: bool = False,
    use_volume_filter: bool = False,
) -> tuple[list[float], list[float]]:
    """Return sorted support/resistance prices from unmitigated swings on candle history."""
    levels = unmitigated_levels_for_candles(
        candles,
        swing_length=swing_length,
        atr_adaptive=atr_adaptive,
        use_atr_filter=use_atr_filter,
        use_volume_filter=use_volume_filter,
    )
    return supports_and_resistances_from_levels(levels)


async def get_unmitigated_levels_for_symbol(
    db,
    account: dict,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 500,
    swing_length: int = DEFAULT_SWING_LENGTH,
    atr_adaptive: bool = False,
    use_atr_filter: bool = False,
    use_volume_filter: bool = False,
) -> dict[str, Any]:
    """Mongo-first candle load + unmitigated swing levels for a symbol/timeframe."""
    candles = await get_recent_chart_candles(
        db,
        account,
        symbol,
        timeframe,
        limit=min(int(limit), 5000),
        min_bars=max(20, 2 * int(swing_length) + 1),
        force_broker_refresh=False,
    )
    levels = unmitigated_levels_for_candles(
        candles,
        swing_length=swing_length,
        atr_adaptive=atr_adaptive,
        use_atr_filter=use_atr_filter,
        use_volume_filter=use_volume_filter,
    )
    supports, resistances = supports_and_resistances_from_levels(levels)
    return {
        "timeframe": normalize_timeframe(timeframe),
        "bar_count": len(candles),
        "swing_length": int(swing_length),
        "levels": levels,
        "supports": supports,
        "resistances": resistances,
    }
