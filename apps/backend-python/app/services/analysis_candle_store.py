from datetime import datetime, timezone

from pymongo import UpdateOne


ANALYSIS_CANDLE_COLLECTION = "analysis_candles"


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _broker_cache_key(account: dict) -> str:
    meta_profile = account.get("meta_profile") or {}
    server = str(meta_profile.get("server") or "").strip().upper()
    broker_type = str(meta_profile.get("type") or "").strip().upper()
    account_currency = str(account.get("account_currency") or meta_profile.get("currency") or "").strip().upper()
    if server:
        return "|".join(part for part in [server, broker_type, account_currency] if part)
    return f"METAACCOUNT|{str(account.get('account_id') or '').upper()}"


def _normalize_timeframe(value: str) -> str:
    text = str(value or "").strip().upper()
    if text in {"M5", "5M", "5MIN", "5MINUTE"}:
        return "5m"
    if text in {"M15", "15M", "15MIN", "15MINUTE"}:
        return "15m"
    if text in {"H1", "1H", "1HR", "1HOUR"}:
        return "1h"
    raise ValueError("timeframe must be M5, M15 or H1.")


def _candle_query(account: dict, symbol: str, timeframe: str) -> dict:
    return {
        "broker_key": _broker_cache_key(account),
        "symbol": str(symbol or "").upper(),
        "timeframe": timeframe,
    }


def save_candle_batch(db, account: dict, symbol: str, timeframe: str, candles: list[dict]):
    normalized_timeframe = _normalize_timeframe(timeframe)
    operations = []
    broker_key = _broker_cache_key(account)
    meta_profile = account.get("meta_profile") or {}
    for candle in candles:
        candle_time = candle.get("time")
        if not candle_time:
            continue
        if hasattr(candle_time, "tzinfo"):
            dt_value = candle_time if candle_time.tzinfo else candle_time.replace(tzinfo=timezone.utc)
        else:
            dt_value = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00"))
        timestamp_utc = _utc_naive(dt_value)
        operations.append(
            UpdateOne(
                {**_candle_query(account, symbol, normalized_timeframe), "timestamp": timestamp_utc},
                {
                    "$set": {
                        "broker_key": broker_key,
                        "broker_server": str(meta_profile.get("server") or ""),
                        "broker_type": str(meta_profile.get("type") or ""),
                        "account_currency": str(account.get("account_currency") or meta_profile.get("currency") or ""),
                        "meta_account_id": str(account.get("account_id") or ""),
                        "open": float(candle.get("open") or 0.0),
                        "high": float(candle.get("high") or 0.0),
                        "low": float(candle.get("low") or 0.0),
                        "close": float(candle.get("close") or 0.0),
                        "updated_at": datetime.utcnow(),
                    },
                    "$setOnInsert": {"created_at": datetime.utcnow()},
                },
                upsert=True,
            )
        )
    if operations:
        db[ANALYSIS_CANDLE_COLLECTION].bulk_write(operations, ordered=False)


def load_stored_candles_between(db, account: dict, symbol: str, timeframe: str, start_utc: datetime, end_utc: datetime) -> list[dict]:
    docs = list(
        db[ANALYSIS_CANDLE_COLLECTION]
        .find(
            {
                **_candle_query(account, symbol, _normalize_timeframe(timeframe)),
                "timestamp": {"$gte": _utc_naive(start_utc), "$lt": _utc_naive(end_utc)},
            }
        )
        .sort("timestamp", 1)
    )
    return [
        {
            "time": doc["timestamp"].replace(tzinfo=timezone.utc),
            "open": float(doc["open"]),
            "high": float(doc["high"]),
            "low": float(doc["low"]),
            "close": float(doc["close"]),
        }
        for doc in docs
    ]
