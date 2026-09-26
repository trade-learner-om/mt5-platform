import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.order_placement import is_market_closed_error, next_monday_0430_ist
from app.services.risk import calc_quantity, calc_risk_amount_from_quantity


IST = ZoneInfo("Asia/Kolkata")


class MarketClosedDeferHelpersTests(unittest.TestCase):
    def test_is_market_closed_error(self):
        self.assertTrue(is_market_closed_error(Exception("MT5 order rejected: retcode=10018 comment=Market closed")))
        self.assertTrue(is_market_closed_error(Exception("market closed")))
        self.assertFalse(is_market_closed_error(Exception("MT5 order rejected: retcode=10015 comment=Invalid price")))

    def test_next_monday_0430_before_monday_gate(self):
        # Sunday 10:00 IST -> upcoming Monday 04:30 IST
        sunday = datetime(2026, 9, 20, 10, 0, tzinfo=IST)
        result = next_monday_0430_ist(sunday).astimezone(IST)
        self.assertEqual(result.weekday(), 0)
        self.assertEqual(result.hour, 4)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.date().isoformat(), "2026-09-21")

    def test_next_monday_0430_after_monday_gate_rolls_forward(self):
        monday_after = datetime(2026, 9, 21, 5, 0, tzinfo=IST)
        result = next_monday_0430_ist(monday_after).astimezone(IST)
        self.assertEqual(result.date().isoformat(), "2026-09-28")
        self.assertEqual(result.hour, 4)
        self.assertEqual(result.minute, 30)

    def test_risk_quantity_round_trip_gold(self):
        entry = 2650.0
        stop = 2640.0
        risk = 100.0
        qty = calc_quantity("XAUUSD", risk, entry, stop)
        self.assertGreater(qty, 0)
        recovered = calc_risk_amount_from_quantity("XAUUSD", qty, entry, stop)
        self.assertAlmostEqual(recovered, risk, delta=risk * 0.15)


if __name__ == "__main__":
    unittest.main()
