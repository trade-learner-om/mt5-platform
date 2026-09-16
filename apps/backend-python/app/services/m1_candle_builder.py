from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from .candle_history import upsert_candles

M1_CANDLE_COLLECTION = "m1_candles"


def _mt5_chart_price(price_tick: dict) -> Optional[float]:
    bid = price_tick.get("bid")
    if bid is not None:
        return float(bid)
    fallback = price_tick.get("price")
    if fallback is not None:
        return float(fallback)
    ask = price_tick.get("ask")
    if ask is None:
        return None
    return float(ask)


def _current_price(price_tick: dict) -> Optional[float]:
    return _mt5_chart_price(price_tick)


def _minute_start(value: datetime) -> datetime:
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)


class M1CandleBuilder:
    def handle_tick(self, db, user_id: str, account: dict, price_tick: dict, tick_time: datetime):
        symbol = str(price_tick.get("symbol") or "").upper().strip()
        price = _mt5_chart_price(price_tick)
        if not symbol or price is None or not account:
            return

        user_oid = ObjectId(user_id)
        account_db_id = account.get("_id")
        minute = _minute_start(tick_time)
        now = datetime.utcnow()
        query = {
            "user_id": user_oid,
            "account_id": account_db_id,
            "symbol": symbol,
            "timeframe": "M1",
            "minute": minute,
        }
        existing = db[M1_CANDLE_COLLECTION].find_one(query)
        if existing:
            high = max(float(existing.get("high") or price), price)
            low = min(float(existing.get("low") or price), price)
            db[M1_CANDLE_COLLECTION].update_one(
                query,
                {
                    "$set": {
                        "high": high,
                        "low": low,
                        "close": price,
                        "bid": price_tick.get("bid"),
                        "ask": price_tick.get("ask"),
                        "last_tick_at": tick_time.replace(tzinfo=None) if tick_time.tzinfo else tick_time,
                        "updated_at": now,
                    },
                    "$inc": {"tick_count": 1},
                },
            )
            upsert_candles(
                db,
                account,
                symbol,
                "M1",
                [
                    {
                        "time": minute,
                        "open": existing.get("open") or price,
                        "high": high,
                        "low": low,
                        "close": price,
                        "volume": int(existing.get("tick_count") or 0) + 1,
                        "source": "MT5",
                    }
                ],
            )
            return

        db[M1_CANDLE_COLLECTION].insert_one(
            {
                **query,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "bid": price_tick.get("bid"),
                "ask": price_tick.get("ask"),
                "tick_count": 1,
                "first_tick_at": tick_time.replace(tzinfo=None) if tick_time.tzinfo else tick_time,
                "last_tick_at": tick_time.replace(tzinfo=None) if tick_time.tzinfo else tick_time,
                "created_at": now,
                "updated_at": now,
            }
        )
        upsert_candles(
            db,
            account,
            symbol,
            "M1",
            [
                {
                    "time": minute,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 1,
                    "source": "MT5",
                }
            ],
        )


m1_candle_builder = M1CandleBuilder()
