import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.metaapi_client import LocalMT5Connection, LocalMT5StreamingPool


class LocalMT5StreamingPoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = MagicMock()
        self.service._session_manager._session_key.return_value = "acct:SERVER:path"
        self.pool = LocalMT5StreamingPool(self.service)

    async def test_acquire_reuses_connection_and_increments_ref_count(self):
        with patch.object(LocalMT5Connection, "connect", new_callable=AsyncMock):
            first = await self.pool.acquire("token", "13883735")
            second = await self.pool.acquire("token", "13883735")

        self.assertIs(first, second)
        self.assertEqual(self.pool._ref_counts["acct:SERVER:path"], 2)

    async def test_release_keeps_polling_until_last_consumer(self):
        with patch.object(LocalMT5Connection, "connect", new_callable=AsyncMock):
            connection = await self.pool.acquire("token", "13883735")
            await self.pool.acquire("token", "13883735")
            connection._shutdown_polling = AsyncMock()

            await self.pool.release("token", "13883735")
            connection._shutdown_polling.assert_not_awaited()

            await self.pool.release("token", "13883735")
            connection._shutdown_polling.assert_awaited_once()
            self.assertNotIn("acct:SERVER:path", self.pool._connections)

    async def test_acquire_from_second_event_loop(self):
        with patch.object(LocalMT5Connection, "connect", new_callable=AsyncMock):
            first = await self.pool.acquire("token", "13883735")

        def _acquire_on_other_loop():
            return asyncio.run(self.pool.acquire("token", "13883735"))

        second = await asyncio.to_thread(_acquire_on_other_loop)
        self.assertIs(first, second)
        self.assertEqual(self.pool._ref_counts["acct:SERVER:path"], 2)


if __name__ == "__main__":
    unittest.main()
