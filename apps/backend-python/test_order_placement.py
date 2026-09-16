import asyncio
import unittest
from unittest.mock import AsyncMock

from app.services.order_placement import (
    build_sl_limit_fallback_info,
    is_invalid_price_error,
    place_pending_order_with_limit_fallback,
)


class OrderPlacementTests(unittest.TestCase):
    def test_is_invalid_price_error(self):
        self.assertTrue(is_invalid_price_error(Exception("MT5 order rejected: retcode=10015 comment=Invalid price")))
        self.assertFalse(is_invalid_price_error(Exception("not enough money")))

    def test_build_sl_limit_fallback_info(self):
        info = build_sl_limit_fallback_info("MT5 order rejected: retcode=10015 comment=Invalid price")
        self.assertEqual(info["requested_order_type"], "SL")
        self.assertEqual(info["placed_order_type"], "LIMIT")
        self.assertIn("Invalid price", info["sl_placement_error"])

    def test_place_limit_directly(self):
        service = AsyncMock()
        service.place_pending_order = AsyncMock(return_value={"orderId": "1"})
        result = asyncio.run(
            place_pending_order_with_limit_fallback(
                service,
                "token",
                "123",
                {"order_type": "LIMIT", "side": "BUY", "entry": 1.1, "stop_loss": 1.0, "quantity": 0.1, "symbol": "EURUSD"},
            )
        )
        self.assertIsNone(result["fallback"])
        service.place_pending_order.assert_awaited_once()

    def test_place_sl_fallback_to_limit(self):
        service = AsyncMock()
        service.place_pending_order = AsyncMock(
            side_effect=[
                Exception("MT5 order rejected: retcode=10015 comment=Invalid price"),
                {"orderId": "2"},
            ]
        )
        payload = {"order_type": "SL", "side": "BUY", "entry": 2650, "stop_loss": 2640, "quantity": 0.1, "symbol": "XAUUSD"}
        result = asyncio.run(place_pending_order_with_limit_fallback(service, "token", "123", payload))
        self.assertEqual(result["order_type"], "LIMIT")
        self.assertIsNotNone(result["fallback"])
        self.assertEqual(service.place_pending_order.await_count, 2)
        second_call_payload = service.place_pending_order.await_args_list[1].args[2]
        self.assertEqual(second_call_payload["order_type"], "LIMIT")


if __name__ == "__main__":
    unittest.main()
