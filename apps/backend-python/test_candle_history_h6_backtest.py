import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

# candle_history pulls metaapi_client → FastAPI/MT5; stub heavy deps for unit tests.
if "pymongo" not in sys.modules:
    pymongo_stub = ModuleType("pymongo")
    pymongo_stub.UpdateOne = MagicMock()
    sys.modules["pymongo"] = pymongo_stub

_metaapi_stub = ModuleType("app.services.metaapi_client")
_metaapi_stub.metaapi_service = MagicMock()
sys.modules["app.services.metaapi_client"] = _metaapi_stub

from app.services.candle_history import (  # noqa: E402
    _aggregate_candles,
    _fetch_mt5_candles_range,
    _infer_bar_phase,
    _normalize_source_candle,
    get_backtest_candles,
)


def _h1_bar(when: datetime, price: float) -> dict:
    return {
        "time": when.isoformat(),
        "open": price,
        "high": price + 1,
        "low": price - 1,
        "close": price + 0.5,
        "tickVolume": 1,
        "volume": 1,
    }


class AggregatedBacktestCandlesTests(unittest.IsolatedAsyncioTestCase):
    def test_aggregate_h6_preserves_xx00_phase(self):
        start = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
        h1 = [_h1_bar(start + timedelta(hours=i), 2000 + i) for i in range(24)]
        bars = _aggregate_candles(h1, "H6")
        self.assertEqual(len(bars), 4)
        self.assertEqual(
            [bar["time"].hour for bar in bars],
            [0, 6, 12, 18],
        )
        self.assertTrue(all(bar["time"].minute == 0 for bar in bars))

    def test_aggregate_h6_preserves_xx30_broker_phase(self):
        start = datetime(2026, 8, 1, 0, 30, tzinfo=timezone.utc)
        h1 = [_h1_bar(start + timedelta(hours=i), 2000 + i) for i in range(24)]
        self.assertEqual(
            _infer_bar_phase([_normalize_source_candle(bar) for bar in h1], 3600),
            1800,
        )
        bars = _aggregate_candles(h1, "H6")
        self.assertEqual(len(bars), 4)
        self.assertEqual(
            [(bar["time"].hour, bar["time"].minute) for bar in bars],
            [(0, 30), (6, 30), (12, 30), (18, 30)],
        )
        self.assertEqual(bars[0]["open"], 2000)
        self.assertEqual(bars[0]["close"], 2005.5)

    async def test_fetch_mt5_candles_range_aggregates_h1_to_h6(self):
        account = {"api_token": "t", "account_id": "1"}
        start = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 1, 23, 0, tzinfo=timezone.utc)
        h1 = [_h1_bar(start + timedelta(hours=i), 2000 + i) for i in range(24)]

        with patch(
            "app.services.candle_history.metaapi_service.get_historical_candles_range",
            new_callable=AsyncMock,
            return_value=h1,
        ) as range_fetch, patch(
            "app.services.candle_history.metaapi_service.get_historical_candles",
            new_callable=AsyncMock,
        ) as from_fetch:
            bars = await _fetch_mt5_candles_range(account, "XAUUSD", "H6", start, end)

        range_fetch.assert_awaited_once()
        args = range_fetch.await_args.args
        self.assertEqual(args[3], "1h")
        from_fetch.assert_not_awaited()
        self.assertEqual(len(bars), 4)
        self.assertEqual(bars[0]["open"], 2000)
        self.assertEqual(bars[0]["close"], 2005.5)

    async def test_get_backtest_candles_h6_uses_range_path(self):
        account = {"api_token": "t", "account_id": "1"}
        start = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)
        h1 = [_h1_bar(start + timedelta(hours=i), 1900 + i) for i in range(24)]
        aggregated = _aggregate_candles(h1, "H6")
        stored: list[dict] = []

        def fake_upsert(_db, _account, _symbol, _timeframe, candles):
            stored.clear()
            stored.extend(candles)

        def fake_load(_db, _account, _symbol, _timeframe, from_time, to_time, limit):
            from_naive = from_time.replace(tzinfo=None) if from_time.tzinfo else from_time
            to_naive = to_time.replace(tzinfo=None) if to_time.tzinfo else to_time
            rows = [candle for candle in stored if from_naive <= candle["time"] <= to_naive]
            return rows[:limit]

        with patch(
            "app.services.candle_history.load_cached_candles",
            side_effect=fake_load,
        ), patch(
            "app.services.candle_history.upsert_candles",
            side_effect=fake_upsert,
        ), patch(
            "app.services.candle_history.delete_cached_candles",
            return_value=0,
        ) as delete_cached, patch(
            "app.services.candle_history.metaapi_service.get_historical_candles_range",
            new_callable=AsyncMock,
            return_value=h1,
        ) as range_fetch, patch(
            "app.services.candle_history._fetch_mt5_candles_from",
            new_callable=AsyncMock,
        ) as from_fetch:
            candles = await get_backtest_candles(
                object(),
                account,
                "XAUUSD",
                start,
                end,
                timeframe="H6",
            )

        range_fetch.assert_awaited()
        from_fetch.assert_not_awaited()
        delete_cached.assert_called_once()
        self.assertGreaterEqual(len(candles), 3)
        self.assertEqual(len(candles), len(aggregated))
        self.assertTrue(all(start.timestamp() <= c["time"] <= end.timestamp() for c in candles))


if __name__ == "__main__":
    unittest.main()
