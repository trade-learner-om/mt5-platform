"""Focused tests for unmitigated swing high/low tracking."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.analytics.market_structure import (
    calculate_unmitigated_levels,
    candles_to_ohlcv_frame,
    detect_swing_pivots,
    supports_and_resistances_from_levels,
)


def _series(rows):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    frame_rows = []
    for index, row in enumerate(rows):
        frame_rows.append(
            {
                "time": start + timedelta(hours=index),
                "Open": row["open"],
                "High": row["high"],
                "Low": row["low"],
                "Close": row["close"],
                "Volume": row.get("volume", 1000),
            }
        )
    return pd.DataFrame(frame_rows)


class UnmitigatedSwingsTests(unittest.TestCase):
    def test_empty_frame_returns_empty(self):
        self.assertEqual(calculate_unmitigated_levels(pd.DataFrame()), [])

    def test_candles_to_ohlcv_normalizes_keys(self):
        candles = [
            {"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10},
            {"time": 2, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 12},
        ]
        frame = candles_to_ohlcv_frame(candles)
        self.assertListEqual(list(frame.columns), ["time", "Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(len(frame), 2)

    def test_swing_low_mitigated_by_later_wick(self):
        rows = []
        for _ in range(30):
            rows.append({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 2000})
        rows[10]["low"] = 90.0
        rows[10]["high"] = 91.0
        rows[10]["close"] = 90.5
        for offset in range(1, 6):
            rows[10 - offset]["low"] = 95.0
            rows[10 + offset]["low"] = 95.0
        rows[20]["low"] = 89.0
        rows[20]["close"] = 91.0
        rows[20]["high"] = 92.0

        frame = _series(rows)
        active = calculate_unmitigated_levels(frame, swing_length=5, use_volume_filter=False)
        active_lows = [lvl for lvl in active if lvl["kind"] == "low" and abs(lvl["price"] - 90.0) < 1e-9]
        self.assertEqual(active_lows, [], msg="Swing low at 90 should be mitigated by later wick")

        all_levels = calculate_unmitigated_levels(
            frame, swing_length=5, use_volume_filter=False, include_mitigated=True
        )
        mitigated_lows = [
            lvl
            for lvl in all_levels
            if lvl["kind"] == "low" and abs(lvl["price"] - 90.0) < 1e-9 and lvl["mitigated"]
        ]
        self.assertTrue(mitigated_lows)
        self.assertEqual(mitigated_lows[0]["mitigated_at_index"], 20)

    def test_unmitigated_swing_high_survives(self):
        rows = []
        for _ in range(30):
            rows.append({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 2000})
        rows[10]["high"] = 110.0
        rows[10]["low"] = 109.0
        rows[10]["close"] = 109.5
        for offset in range(1, 6):
            rows[10 - offset]["high"] = 102.0
            rows[10 + offset]["high"] = 102.0
        for i in range(11, 30):
            rows[i]["high"] = 105.0
            rows[i]["close"] = 104.0

        frame = _series(rows)
        active = calculate_unmitigated_levels(frame, swing_length=5, use_volume_filter=False)
        highs = [lvl for lvl in active if lvl["kind"] == "high" and abs(lvl["price"] - 110.0) < 1e-9]
        self.assertTrue(highs, msg="Swing high at 110 should remain unmitigated")
        self.assertEqual(highs[0]["direction"], "SHORT")
        supports, resistances = supports_and_resistances_from_levels(active)
        self.assertIn(110.0, resistances)
        self.assertNotIn(110.0, supports)

    def test_detect_swing_pivots_basic(self):
        rows = []
        for _ in range(25):
            rows.append({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 2000})
        rows[12]["high"] = 120.0
        for offset in range(1, 6):
            rows[12 - offset]["high"] = 105.0
            rows[12 + offset]["high"] = 105.0
        frame = _series(rows)
        high_mask, low_mask = detect_swing_pivots(frame, swing_length=5, use_volume_filter=False)
        self.assertTrue(bool(high_mask.iloc[12]))
        self.assertFalse(bool(low_mask.iloc[12]))

    def test_volume_sigma_threshold_rejects_weak_pivot(self):
        rows = []
        for i in range(40):
            volume = 1000 if i % 2 == 0 else 100
            rows.append({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": volume})
        rows[20]["high"] = 130.0
        rows[20]["low"] = 129.0
        rows[20]["close"] = 129.5
        rows[20]["volume"] = 600  # above mean of alternating series? mean ~550; with sigma may fail
        for offset in range(1, 6):
            rows[20 - offset]["high"] = 105.0
            rows[20 + offset]["high"] = 105.0

        frame = _series(rows)
        without = detect_swing_pivots(frame, swing_length=5, use_volume_filter=False)
        with_filter = detect_swing_pivots(frame, swing_length=5, use_volume_filter=True, volume_sigma=1.5)
        self.assertTrue(bool(without[0].iloc[20]))
        self.assertFalse(bool(with_filter[0].iloc[20]))

    def test_atr_filter_drops_tight_pivot(self):
        rows = []
        for _ in range(40):
            # Wide ATR environment
            rows.append({"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0, "volume": 2000})
        # Tiny local fractal high relative to ATR
        rows[20]["high"] = 110.5
        rows[20]["low"] = 109.5
        rows[20]["close"] = 110.0
        for offset in range(1, 6):
            rows[20 - offset]["high"] = 110.2
            rows[20 + offset]["high"] = 110.2

        frame = _series(rows)
        no_atr, _ = detect_swing_pivots(frame, swing_length=5, use_atr_filter=False, use_volume_filter=False)
        with_atr, _ = detect_swing_pivots(
            frame, swing_length=5, use_atr_filter=True, atr_multiplier=0.5, use_volume_filter=False
        )
        self.assertTrue(bool(no_atr.iloc[20]))
        self.assertFalse(bool(with_atr.iloc[20]))


if __name__ == "__main__":
    unittest.main()
