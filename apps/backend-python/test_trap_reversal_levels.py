"""Trap Reversal H1 indexing uses the shared unmitigated swing detector."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.trap_reversal_automation import index_h1_levels


class TrapReversalLevelIndexTests(unittest.TestCase):
    def test_index_h1_keeps_unmitigated_high(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(30):
            rows.append(
                {
                    "time": start + timedelta(hours=i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 2000,
                }
            )
        rows[10]["high"] = 110.0
        rows[10]["low"] = 109.0
        rows[10]["close"] = 109.5
        for offset in range(1, 6):
            rows[10 - offset]["high"] = 102.0
            rows[10 + offset]["high"] = 102.0
        for i in range(11, 30):
            rows[i]["high"] = 105.0
            rows[i]["close"] = 104.0

        supports, resistances = index_h1_levels(pd.DataFrame(rows))
        self.assertIn(110.0, resistances)
        self.assertEqual(supports, [])


if __name__ == "__main__":
    unittest.main()
