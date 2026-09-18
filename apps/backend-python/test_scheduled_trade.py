import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from app.services.order_placement import place_pending_order_with_limit_fallback
from app.services.scheduled_trade_levels import (
    buy_entry_sl,
    entry_sl_for_side,
    is_oversized_signal_candle,
    resolve_side_from_level,
    sell_entry_sl,
    usable_target,
)


RUNTIME_PATH = Path(__file__).resolve().parent / "app" / "services" / "scheduled_trade_runtime.py"


class ScheduledTradeLevelsTests(unittest.TestCase):
    def test_direction_from_level(self):
        self.assertEqual(resolve_side_from_level(2651, 2650), "SELL")
        self.assertEqual(resolve_side_from_level(2649, 2650), "BUY")
        with self.assertRaises(ValueError):
            resolve_side_from_level(2650, 2650)

    def test_entry_sl_formulas(self):
        red = {"open": 2652, "high": 2653, "low": 2648, "close": 2649}
        green = {"open": 2648, "high": 2652, "low": 2647, "close": 2651}
        point = 0.01
        sell_entry, sell_sl = sell_entry_sl(red, point)
        self.assertAlmostEqual(sell_entry, 2648 - point)
        self.assertAlmostEqual(sell_sl, 2653 + 3 * point)
        buy_entry, buy_sl = buy_entry_sl(green, point)
        self.assertAlmostEqual(buy_entry, 2652 + point)
        self.assertAlmostEqual(buy_sl, 2647 - 3 * point)
        self.assertEqual(entry_sl_for_side("SELL", red, point), (sell_entry, sell_sl))

    def test_oversized_candle_skip(self):
        gold_ok = {"high": 2650.0, "low": 2640.1, "open": 2649, "close": 2641}
        gold_big = {"high": 2650.0, "low": 2639.8, "open": 2649, "close": 2640}
        self.assertFalse(is_oversized_signal_candle(gold_ok, "XAUUSD"))
        self.assertTrue(is_oversized_signal_candle(gold_big, "XAUUSD"))
        fx_ok = {"high": 1.10000, "low": 1.09920, "open": 1.09990, "close": 1.09930}
        fx_big = {"high": 1.10150, "low": 1.10000, "open": 1.10140, "close": 1.10010}
        self.assertFalse(is_oversized_signal_candle(fx_ok, "EURUSD"))
        self.assertTrue(is_oversized_signal_candle(fx_big, "EURUSD"))

    def test_oversized_candle_respects_custom_max(self):
        candle = {"high": 2650.0, "low": 2640.0, "open": 2649, "close": 2641}  # 100 pips gold
        self.assertFalse(is_oversized_signal_candle(candle, "XAUUSD", max_pips=100))
        self.assertTrue(is_oversized_signal_candle(candle, "XAUUSD", max_pips=99))
        fx = {"high": 1.10100, "low": 1.10000, "open": 1.10090, "close": 1.10010}  # 10 pips
        self.assertFalse(is_oversized_signal_candle(fx, "EURUSD", max_pips=10))
        self.assertTrue(is_oversized_signal_candle(fx, "EURUSD", max_pips=9))

    def test_usable_target_requires_4r(self):
        self.assertIsNone(usable_target("SELL", 100.0, 101.0, 97.0))
        self.assertEqual(usable_target("SELL", 100.0, 101.0, 96.0), 96.0)
        self.assertEqual(usable_target("BUY", 100.0, 99.0, 104.0), 104.0)


class ScheduledTradePlacementTests(unittest.TestCase):
    def test_primary_invalid_price_falls_back_to_limit(self):
        service = AsyncMock()
        service.place_pending_order = AsyncMock(
            side_effect=[
                Exception("MT5 order rejected: retcode=10015 comment=Invalid price"),
                {"orderId": "limit-1"},
            ]
        )
        payload = {"order_type": "SL", "side": "SELL", "entry": 2648, "stop_loss": 2653, "quantity": 0.1, "symbol": "XAUUSD"}
        result = asyncio.run(place_pending_order_with_limit_fallback(service, "token", "acc", payload))
        self.assertEqual(result["order_type"], "LIMIT")
        self.assertIsNotNone(result["fallback"])
        self.assertEqual(service.place_pending_order.await_count, 2)

    def test_retry_leg_uses_direct_sl_not_fallback_helper(self):
        source = RUNTIME_PATH.read_text(encoding="utf-8")
        start = source.index("async def _place_retry_immediate")
        end = source.index("async def _insert_order_doc", start)
        method = source[start:end]
        self.assertIn("place_pending_order(", method)
        self.assertNotIn("place_pending_order_with_limit_fallback", method)
        self.assertIn("LIMIT fallback disabled", method)
        self.assertIn("RETRY_INITIATED", source)
        self.assertIn("RETRY_ORDER_PLACED", source)


if __name__ == "__main__":
    unittest.main()
