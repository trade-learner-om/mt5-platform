"""Unit tests for unmitigated swing target + slice helpers."""

from __future__ import annotations

import unittest

from app.services.structure_swings import (
    merge_levels_within_pct,
    resolve_unmitigated_swing_target,
    slice_highs_and_lows,
    target_4r_price,
)


class StructureSwingsHelperTests(unittest.TestCase):
    def test_target_4r_buy_and_sell(self):
        self.assertAlmostEqual(target_4r_price("BUY", 100.0, 99.0), 104.0)
        self.assertAlmostEqual(target_4r_price("SELL", 100.0, 101.0), 96.0)

    def test_buy_picks_farther_structure_high(self):
        self.assertAlmostEqual(resolve_unmitigated_swing_target("BUY", 100.0, 99.0, 110.0), 110.0)
        self.assertAlmostEqual(resolve_unmitigated_swing_target("BUY", 100.0, 99.0, 102.0), 104.0)

    def test_sell_picks_farther_structure_low(self):
        self.assertAlmostEqual(resolve_unmitigated_swing_target("SELL", 100.0, 101.0, 90.0), 90.0)
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

    def test_merge_within_one_percent(self):
        levels = [
            {"kind": "low", "price": 100.0, "time": "a", "index": 1, "mitigated": False},
            {"kind": "low", "price": 100.5, "time": "b", "index": 2, "mitigated": False},
            {"kind": "low", "price": 90.0, "time": "c", "index": 3, "mitigated": False},
            {"kind": "high", "price": 200.0, "time": "d", "index": 4, "mitigated": False},
            {"kind": "high", "price": 201.0, "time": "e", "index": 5, "mitigated": False},
            {"kind": "high", "price": 220.0, "time": "f", "index": 6, "mitigated": False},
        ]
        merged = merge_levels_within_pct(levels, pct=0.01)
        low_prices = sorted(float(item["price"]) for item in merged if item["kind"] == "low")
        high_prices = sorted(float(item["price"]) for item in merged if item["kind"] == "high")
        self.assertEqual(low_prices, [90.0, 100.0])
        self.assertEqual(high_prices, [201.0, 220.0])

    def test_merge_then_slice_fills_count(self):
        levels = [
            {"kind": "low", "price": 99.0, "time": "t0", "index": 0, "mitigated": False},
            {"kind": "low", "price": 99.2, "time": "t1", "index": 1, "mitigated": False},
            {"kind": "low", "price": 95.0, "time": "t2", "index": 2, "mitigated": False},
            {"kind": "low", "price": 90.0, "time": "t3", "index": 3, "mitigated": False},
            {"kind": "high", "price": 105.0, "time": "t4", "index": 4, "mitigated": False},
            {"kind": "high", "price": 105.5, "time": "t5", "index": 5, "mitigated": False},
            {"kind": "high", "price": 110.0, "time": "t6", "index": 6, "mitigated": False},
        ]
        merged = merge_levels_within_pct(levels)
        highs, lows = slice_highs_and_lows(merged, swing_count=2, mid_price=100.0)
        self.assertEqual(len(highs), 2)
        self.assertEqual(len(lows), 2)


if __name__ == "__main__":
    unittest.main()
