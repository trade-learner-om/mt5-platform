"""Regression tests for the analytics OHLCV helpers (no removed analysis routes)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.analytics.market_structure import (
    calculate_unmitigated_levels,
    candles_to_ohlcv_frame,
)


def _series(rows):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    frame_rows = []
    for index, row in enumerate(rows):
        frame_rows.append(
            {
                "time": start + timedelta(hours=index),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume", 1000),
            }
        )
    return pd.DataFrame(frame_rows)


class MarketStructureHelperTests(unittest.TestCase):
    def test_empty_input_returns_empty_levels(self):
        self.assertEqual(calculate_unmitigated_levels(pd.DataFrame()), [])

    def test_lowercase_candle_columns_normalize(self):
        frame = _series(
            [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 2000} for _ in range(25)]
        )
        levels = calculate_unmitigated_levels(frame, swing_length=5)
        self.assertIsInstance(levels, list)

    def test_candles_helper_matches_frame_path(self):
        candles = [
            {"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000}
            for i in range(30)
        ]
        candles[12]["high"] = 120.0
        for offset in range(1, 6):
            candles[12 - offset]["high"] = 105.0
            candles[12 + offset]["high"] = 105.0
        frame = candles_to_ohlcv_frame(candles)
        levels = calculate_unmitigated_levels(frame, swing_length=5, use_volume_filter=False)
        highs = [lvl for lvl in levels if lvl["kind"] == "high" and abs(lvl["price"] - 120.0) < 1e-9]
        self.assertTrue(highs)


if __name__ == "__main__":
    unittest.main()
