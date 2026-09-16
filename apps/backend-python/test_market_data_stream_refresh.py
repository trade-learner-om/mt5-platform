import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.services.market_data_stream import MarketDataStreamManager, STREAM_REFRESH_DEBOUNCE_SECONDS


class MarketDataStreamRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = MarketDataStreamManager.__new__(MarketDataStreamManager)
        self.manager._sessions = {}
        self.manager._last_stream_refresh_at = {}
        self.manager._last_price_tick_at = {}
        self.manager._user_stream_lock = lambda user_id: _NoopLock()

    def test_stream_refresh_is_debounced_within_window(self):
        user_id = "user-1"
        self.manager.mark_stream_refreshed(user_id)
        self.assertTrue(self.manager.stream_refresh_is_debounced(user_id))

    def test_stream_refresh_not_debounced_after_window(self):
        user_id = "user-1"
        self.manager._last_stream_refresh_at[user_id] = datetime.now(timezone.utc) - timedelta(
            seconds=STREAM_REFRESH_DEBOUNCE_SECONDS + 1
        )
        self.assertFalse(self.manager.stream_refresh_is_debounced(user_id))

    def test_primary_symbols_cover_execution_subset(self):
        user_id = "user-1"
        self.manager._sessions[user_id] = {
            "kind": "primary",
            "account_db_id": "acc-1",
            "symbols": ["XAUUSD", "AUDUSD"],
        }
        self.assertTrue(self.manager._primary_symbols_cover(user_id, "acc-1", {"XAUUSD"}))
        self.assertFalse(self.manager._primary_symbols_cover(user_id, "acc-1", {"EURUSD"}))

    async def test_refresh_live_stream_skips_full_setup_when_debounced(self):
        user_id = "user-1"
        self.manager.mark_stream_refreshed(user_id)
        self.manager._sessions[user_id] = {
            "kind": "primary",
            "symbols": ["XAUUSD"],
            "started_at": datetime.now(timezone.utc),
        }
        self.manager._ensure_session_polling = AsyncMock()
        on_update = AsyncMock()
        db = MagicMock()

        await self.manager.refresh_live_stream(db, user_id, on_update)

        on_update.assert_awaited_once()
        self.manager._ensure_session_polling.assert_awaited()


class _NoopLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


if __name__ == "__main__":
    unittest.main()
