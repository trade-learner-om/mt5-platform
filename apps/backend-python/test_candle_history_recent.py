import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.services.candle_history import get_recent_chart_candles


class RecentChartCandlesTests(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_to_mt5_when_cache_has_fewer_than_min_bars(self):
        account = {"api_token": "t", "account_id": "1"}
        sparse = [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1}]
        fetched = [
            {"time": datetime(2026, 7, 20, 0, tzinfo=timezone.utc), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1},
            {"time": datetime(2026, 7, 20, 4, tzinfo=timezone.utc), "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 1},
            {"time": datetime(2026, 7, 20, 8, tzinfo=timezone.utc), "open": 2.0, "high": 3.0, "low": 1.5, "close": 2.5, "volume": 1},
        ]

        with patch("app.services.candle_history.get_chart_candles", new_callable=AsyncMock, return_value=sparse), patch(
            "app.services.candle_history._fetch_mt5_candles",
            new_callable=AsyncMock,
            return_value=fetched,
        ), patch("app.services.candle_history.upsert_candles") as upsert:
            candles = await get_recent_chart_candles(
                db=object(),
                account=account,
                symbol="XAUUSD",
                timeframe="4h",
                limit=12,
                min_bars=2,
            )

        self.assertGreaterEqual(len(candles), 2)
        upsert.assert_called_once()

    async def test_returns_cached_candles_when_enough_bars(self):
        account = {"api_token": "t", "account_id": "1"}
        cached = [
            {"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1},
            {"time": 2, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 1},
        ]

        with patch("app.services.candle_history.get_chart_candles", new_callable=AsyncMock, return_value=cached), patch(
            "app.services.candle_history._fetch_mt5_candles",
            new_callable=AsyncMock,
        ) as fetch:
            candles = await get_recent_chart_candles(
                db=object(),
                account=account,
                symbol="XAUUSD",
                timeframe="4h",
            )

        self.assertEqual(len(candles), 2)
        fetch.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
