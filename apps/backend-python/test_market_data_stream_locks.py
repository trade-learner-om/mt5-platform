import asyncio
import unittest
from weakref import WeakKeyDictionary

from app.services.market_data_stream import MarketDataStreamManager


class MarketDataStreamLockTests(unittest.TestCase):
    def test_user_stream_lock_is_scoped_to_running_event_loop(self):
        manager = object.__new__(MarketDataStreamManager)
        manager._stream_ensure_locks = WeakKeyDictionary()

        async def capture_lock():
            return manager._user_stream_lock("user-1")

        loop_a = asyncio.new_event_loop()
        loop_b = asyncio.new_event_loop()
        try:
            lock_a = loop_a.run_until_complete(capture_lock())
            lock_b = loop_b.run_until_complete(capture_lock())
            self.assertIsNot(lock_a, lock_b)

            loop_a.run_until_complete(lock_a.acquire())
            lock_a.release()

            with self.assertRaises(RuntimeError):
                loop_b.run_until_complete(lock_a.acquire())
        finally:
            loop_a.close()
            loop_b.close()


if __name__ == "__main__":
    unittest.main()
