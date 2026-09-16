import unittest
from datetime import datetime, timezone

from app.services.metaapi_client import (
    booked_profit_from_deals,
    closed_trade_net_profit_from_deals,
    match_order_to_trade_history,
    merge_realized_pl_on_close,
    needs_active_booked_pl_resolution,
    needs_closed_realized_pl_resolution,
    order_has_partial_booking,
)


class ClosedOrderPlTests(unittest.TestCase):
    def test_merge_realized_pl_on_close_adds_running_pl(self):
        order = {"realized_pl": 12.5, "unrealized_pl": 37.5}
        self.assertEqual(merge_realized_pl_on_close(order), 50.0)

    def test_merge_realized_pl_on_close_keeps_none_without_unrealized(self):
        order = {"realized_pl": None, "unrealized_pl": None}
        self.assertIsNone(merge_realized_pl_on_close(order))

    def test_needs_resolution_for_zero_with_position(self):
        order = {"status": "CLOSED", "realized_pl": 0, "meta_position_id": "12345"}
        self.assertTrue(needs_closed_realized_pl_resolution(order))

    def test_match_order_to_trade_history_by_position_id(self):
        order = {"meta_position_id": "12345", "symbol": "XAUUSD"}
        rows = [
            {
                "position_id": "12345",
                "symbol": "XAUUSD",
                "net_profit": 42.5,
                "is_running": False,
            }
        ]
        self.assertEqual(match_order_to_trade_history(order, rows), 42.5)

    def test_booked_profit_from_deals_uses_exit_deals_only(self):
        deals = [
            {"type": 0, "entry": 0, "order": 67890, "position_id": 12345, "symbol": "XAUUSD", "profit": 0.0, "commission": -1.0, "swap": 0.0},
            {"type": 1, "entry": 1, "order": 67891, "position_id": 12345, "symbol": "XAUUSD", "profit": 42.5, "commission": -0.5, "swap": 0.25},
        ]
        self.assertEqual(booked_profit_from_deals(deals, position_id="12345"), 42.25)
        self.assertEqual(closed_trade_net_profit_from_deals(deals, position_id="12345"), 41.25)

    def test_needs_active_resolution_for_partial_status(self):
        order = {"status": "PARTIALLY_CLOSED", "realized_pl": 0, "meta_position_id": "12345", "quantity": 1.0, "position_quantity": 0.5}
        self.assertTrue(needs_active_booked_pl_resolution(order))
        self.assertTrue(order_has_partial_booking(order))

    def test_match_order_to_trade_history_by_open_time(self):
        opened = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
        order = {"symbol": "EURUSD", "opened_at": opened}
        rows = [
            {
                "position_id": "999",
                "symbol": "EURUSD",
                "open_time": opened.isoformat(),
                "net_profit": 15.0,
                "is_running": False,
            }
        ]
        self.assertEqual(match_order_to_trade_history(order, rows), 15.0)


if __name__ == "__main__":
    unittest.main()
