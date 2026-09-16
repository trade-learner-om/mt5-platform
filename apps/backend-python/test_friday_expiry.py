import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.metaapi_client import (
    _coming_friday_expiry_utc,
    _mt5_friday_expiration_timestamp,
    _symbol_supports_specified_expiration,
)

IST = ZoneInfo("Asia/Kolkata")


class FridayExpiryTests(unittest.TestCase):
    def test_midweek_resolves_to_coming_friday_2359_ist(self):
        # Wed 2026-06-24 12:00 UTC -> coming Friday is 2026-06-26.
        reference = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
        result = _coming_friday_expiry_utc(reference)
        result_ist = result.astimezone(IST)
        self.assertEqual(result_ist.weekday(), 4)  # Friday
        self.assertEqual((result_ist.hour, result_ist.minute, result_ist.second), (23, 59, 59))
        self.assertEqual(result_ist.date().isoformat(), "2026-06-26")
        # 23:59:59 IST == 18:29:59 UTC
        self.assertEqual(result, datetime(2026, 6, 26, 18, 29, 59, tzinfo=timezone.utc))

    def test_after_friday_close_rolls_to_next_friday(self):
        # Exactly Friday 23:59:59 IST should roll forward a week.
        reference = datetime(2026, 6, 26, 18, 29, 59, tzinfo=timezone.utc)
        result = _coming_friday_expiry_utc(reference).astimezone(IST)
        self.assertEqual(result.weekday(), 4)
        self.assertEqual(result.date().isoformat(), "2026-07-03")

    def test_weekend_resolves_to_next_friday(self):
        # Saturday should target the following Friday.
        reference = datetime(2026, 6, 27, 6, 0, 0, tzinfo=timezone.utc)
        result = _coming_friday_expiry_utc(reference).astimezone(IST)
        self.assertEqual(result.weekday(), 4)
        self.assertEqual(result.date().isoformat(), "2026-07-03")

    def test_expiration_timestamp_applies_broker_offset(self):
        utc_now = int(datetime.now(timezone.utc).timestamp())
        tick = SimpleNamespace(time=utc_now + 7200)  # broker is UTC+2
        target = int(_coming_friday_expiry_utc().timestamp())
        result = _mt5_friday_expiration_timestamp(tick)
        self.assertAlmostEqual(result - target, 7200, delta=2)

    def test_expiration_timestamp_without_tick_time(self):
        result = _mt5_friday_expiration_timestamp(SimpleNamespace(time=0))
        target = int(_coming_friday_expiry_utc().timestamp())
        self.assertAlmostEqual(result, target, delta=2)

    def test_specified_expiration_support(self):
        self.assertTrue(_symbol_supports_specified_expiration(SimpleNamespace(expiration_mode=4)))
        self.assertTrue(_symbol_supports_specified_expiration(SimpleNamespace(expiration_mode=15)))
        self.assertFalse(_symbol_supports_specified_expiration(SimpleNamespace(expiration_mode=3)))
        self.assertFalse(_symbol_supports_specified_expiration(SimpleNamespace(expiration_mode=0)))


if __name__ == "__main__":
    unittest.main()
