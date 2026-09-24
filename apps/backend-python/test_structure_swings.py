"""Unit tests for unmitigated swing target + slice helpers."""

from __future__ import annotations

import unittest

from app.services.structure_swings import (
    resolve_unmitigated_swing_target,
    slice_highs_and_lows,
    target_4r_price,
)


class StructureSwingsHelperTests(unittest.TestCase):
    def test_target_4r_buy_and_sell(self):
        self.assertAlmostEqual(target_4r_price("BUY", 100.0, 99.0), 104.0)
        self.assertAlmostEqual(target_4r_price("SELL", 100.0, 101.0), 96.0)

    def test_buy_picks_farther_structure_high(self):
        # 4R = 104; structure high 110 → 110
        self.assertAlmostEqual(resolve_unmitigated_swing_target("BUY", 100.0, 99.0, 110.0), 110.0)
        # structure closer than 4R → keep 4R
        self.assertAlmostEqual(resolve_unmitigated_swing_target("BUY", 100.0, 99.0, 102.0), 104.0)

    def test_sell_picks_farther_structure_low(self):
        # 4R = 96; structure low 90 → 90
        self.assertAlmostEqual(resolve_unmitigated_swing_target("SELL", 100.0, 101.0, 90.0), 90.0)
        # structure closer → keep 4R
        self.assertAlmostEqual(resolve_unmitigated_swing_target("SELL", 100.0, 101.0, 98.0), 96.0)

    def test_slice_nearest_to_mid(self):
        levels = [
            {"kind": "high", "price": 120.0, "time": "t1", "index": 1, "mitigated": False},
            {"kind": "high", "price": 105.0, "time": "t2", "index": 2, "mitigated": False},
            {"kind": "high", "price": 108.0, "time": "t3", "index": 3, "mitigated": False},
            {"kind": "low", "price": 80.0, "time": "t4", "index": 4, "mitigated": False},
            {"kind": "low", "price": 95.0, "time": "t5", "index": 5, "mitigated": False},
            {"kind": "low", "price": 90.0, "time": "t6", "index": 6, "mitigated": False},
        ]
        highs, lows = slice_highs_and_lows(levels, swing_count=2, mid_price=100.0)
        self.assertEqual([row["price"] for row in highs], [108.0, 105.0])
        self.assertEqual([row["price"] for row in lows], [95.0, 90.0])


if __name__ == "__main__":
    unittest.main()
