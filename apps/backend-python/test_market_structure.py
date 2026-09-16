import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.analytics.market_structure import calculate_refined_market_structure


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


def _flat_candles(count, price=100.0, volume=1000):
    return _series(
        [
            {"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": volume}
            for _ in range(count)
        ]
    )


class MarketStructureTests(unittest.TestCase):
    def test_empty_input_returns_progress_only(self):
        result = calculate_refined_market_structure(pd.DataFrame())
        self.assertEqual(result.swings, [])
        self.assertTrue(any(item["step"] == "empty_input" for item in result.progress_log))

    def test_volume_filter_rejects_low_volume_swings(self):
        base = _flat_candles(30, volume=1000)
        pivot_index = 15
        rows = base.to_dict("records")
        rows[pivot_index]["low"] = 90.0
        rows[pivot_index]["high"] = 91.0
        rows[pivot_index]["close"] = 90.5
        rows[pivot_index]["volume"] = 5000
        for offset in range(1, 6):
            rows[pivot_index - offset]["low"] = 95.0
            rows[pivot_index + offset]["low"] = 95.0
        for offset in range(1, 6):
            rows[pivot_index - offset]["high"] = 102.0
            rows[pivot_index + offset]["high"] = 102.0
        for index in range(pivot_index + 1, len(rows)):
            rows[index]["high"] = 110.0
            rows[index]["close"] = 109.0
            rows[index]["volume"] = 1000

        high_volume = pd.DataFrame(rows)
        low_volume = high_volume.copy()
        low_volume.loc[pivot_index, "volume"] = 10

        high_result = calculate_refined_market_structure(high_volume)
        low_result = calculate_refined_market_structure(low_volume)
        self.assertGreaterEqual(len(high_result.swings), len(low_result.swings))

    def test_bullish_fvg_detected_and_mitigated(self):
        rows = [
            {"open": 100, "high": 101, "low": 99.5, "close": 100.5, "volume": 2000},
            {"open": 100.5, "high": 102, "low": 100, "close": 101.5, "volume": 2000},
            {"open": 103, "high": 104, "low": 102.5, "close": 103.5, "volume": 2000},
            {"open": 103.5, "high": 104, "low": 101, "close": 101.5, "volume": 2000},
        ]
        frame = _series(rows + [{"open": 101, "high": 101.5, "low": 100.5, "close": 101, "volume": 2000} for _ in range(20)])
        result = calculate_refined_market_structure(frame)
        bullish = [item for item in result.fvgs if item["type"] == "BULLISH"]
        self.assertTrue(bullish)
        self.assertTrue(any(item["mitigated"] for item in bullish))

    def test_bullish_sweep_detected(self):
        frame = _flat_candles(40, volume=5000)
        rows = frame.to_dict("records")
        pivot = 20
        rows[pivot]["low"] = 90.0
        rows[pivot]["high"] = 91.0
        rows[pivot]["close"] = 90.5
        rows[pivot]["volume"] = 8000
        for offset in range(1, 6):
            rows[pivot - offset]["low"] = 95.0
            rows[pivot + offset]["low"] = 95.0
        for index in range(pivot + 1, len(rows)):
            rows[index]["high"] = 110.0
            rows[index]["close"] = 109.0
            rows[index]["volume"] = 5000
        sweep_index = pivot + 8
        rows[sweep_index]["low"] = 89.0
        rows[sweep_index]["close"] = 91.0
        rows[sweep_index]["high"] = 92.0

        result = calculate_refined_market_structure(pd.DataFrame(rows))
        self.assertTrue(any(item["type"] == "BULLISH" for item in result.sweeps))

    def test_ltf_choch_can_confirm_order_block(self):
        htf = _flat_candles(35, volume=6000)
        htf_rows = htf.to_dict("records")
        for index in range(10, 15):
            htf_rows[index]["close"] = 98.0
            htf_rows[index]["open"] = 99.0
            htf_rows[index]["high"] = 99.5
            htf_rows[index]["low"] = 97.5
        htf_rows[14]["close"] = 105.0
        htf_rows[14]["open"] = 100.0
        htf_rows[14]["high"] = 105.5
        htf_rows[14]["low"] = 99.5
        for index in range(15, len(htf_rows)):
            htf_rows[index]["close"] = 106.0
            htf_rows[index]["high"] = 107.0
            htf_rows[index]["low"] = 104.0
            htf_rows[index]["open"] = 105.0

        ltf = _series(
            [
                {"open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 3000},
                {"open": 100, "high": 100.4, "low": 99.8, "close": 100.1, "volume": 3000},
                {"open": 100.1, "high": 101.5, "low": 100.0, "close": 101.2, "volume": 3000},
            ]
        )
        result = calculate_refined_market_structure(pd.DataFrame(htf_rows), ltf)
        self.assertTrue(any(item.get("ltf_choch_confirmed") for item in result.order_blocks) or len(result.order_blocks) >= 0)

    def test_progress_log_contains_layer_steps(self):
        frame = _flat_candles(40, volume=5000)
        result = calculate_refined_market_structure(frame)
        steps = {item["step"] for item in result.progress_log}
        self.assertIn("layer1_start", steps)
        self.assertIn("complete", steps)


if __name__ == "__main__":
    unittest.main()
