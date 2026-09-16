import unittest
from datetime import datetime, timedelta, timezone

from app.services.master_break_fsm import MasterBreakSideFSM, SideState
from app.services.master_break_levels import (
    coerce_candle_time,
    completed_master_bars,
    is_green,
    is_red,
    long_entry_sl,
    master_high,
    master_low,
    short_entry_sl,
)
from app.services.master_break_settings import MasterBreakSettings


def candle(open_, high, low, close, time=None):
    return {"open": open_, "high": high, "low": low, "close": close, "time": time}


class MasterBreakLevelsTests(unittest.TestCase):
    def test_green_red(self):
        self.assertTrue(is_green(candle(100, 105, 99, 104)))
        self.assertTrue(is_red(candle(104, 105, 99, 100)))
        self.assertFalse(is_green(candle(100, 105, 99, 100)))

    def test_master_high_and_low(self):
        bar = candle(100, 112, 99, 108)
        self.assertEqual(master_high(bar), 112)
        self.assertEqual(master_low(bar), 99)

    def test_short_and_long_entry_sl(self):
        rc = candle(110, 115, 108, 109)
        entry, sl = short_entry_sl(rc, 0.01)
        self.assertAlmostEqual(entry, 107.99)
        self.assertAlmostEqual(sl, 115.01)

        gc = candle(100, 106, 99, 105)
        entry, sl = long_entry_sl(gc, 0.01)
        self.assertAlmostEqual(entry, 106.01)
        self.assertAlmostEqual(sl, 98.99)

    def test_completed_master_bars_drops_in_progress(self):
        now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
        bars = [
            candle(1, 2, 0.5, 1.5, now - timedelta(hours=12)),
            candle(1.5, 2.5, 1.4, 2.0, now - timedelta(hours=6)),
            candle(2.0, 2.2, 1.9, 2.1, now - timedelta(hours=1)),  # in-progress H6
        ]
        completed = completed_master_bars(bars, now=now, timeframe="H6", drop_in_progress=True)
        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[-1]["close"], 2.0)

    def test_coerce_candle_time_accepts_unix_int_and_digit_string(self):
        epoch = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        as_int = coerce_candle_time(epoch)
        as_str = coerce_candle_time(str(epoch))
        self.assertIsNotNone(as_int)
        self.assertEqual(as_int, as_str)
        self.assertEqual(as_int.year, 2026)

    def test_coerce_naive_iso_keeps_broker_face(self):
        as_naive = coerce_candle_time("2026-09-02T06:00:00")
        self.assertIsNotNone(as_naive)
        self.assertIsNone(as_naive.tzinfo)
        self.assertEqual(as_naive.hour, 6)
        as_zulu = coerce_candle_time("2026-09-02T06:00:00+00:00")
        self.assertEqual(as_zulu, datetime(2026, 9, 2, 6, 0, 0))
        # Non-zero offset must keep the written wall face (no astimezone shift).
        as_offset = coerce_candle_time("2026-09-02T06:00:00+05:30")
        self.assertEqual(as_offset, datetime(2026, 9, 2, 6, 0, 0))

    def test_settings_targets_must_sum_100(self):
        ok = MasterBreakSettings.from_mapping(
            {
                "risk_amount": 50,
                "targets": [{"r": 2, "qty_pct": 40}, {"r": 5, "qty_pct": 60}],
            }
        )
        self.assertEqual(ok.master_timeframe, "H6")
        with self.assertRaises(ValueError):
            MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 40}, {"r": 5, "qty_pct": 50}]})
        # float tolerance
        MasterBreakSettings.from_mapping({"targets": [{"r": 1, "qty_pct": 33.33}, {"r": 2, "qty_pct": 66.67}]})

    def test_short_arm_and_invalidate(self):
        settings = MasterBreakSettings.from_mapping(
            {"risk_amount": 100, "breakeven_r": 1, "targets": [{"r": 2, "qty_pct": 100}]}
        )
        fsm = MasterBreakSideFSM(side="SHORT", settings=settings, point=0.01)
        master = candle(108, 112, 107, 111)
        events = fsm.process_master_close(master)
        self.assertEqual(fsm.state, SideState.WAIT_BREAK)
        self.assertEqual(fsm.level, 112)
        self.assertEqual(events[0].payload.get("kind"), "MASTER_HIGH")
        self.assertTrue(any(event.type == "MASTER_LEVEL" for event in events))

        break_bar = candle(111, 113, 110.5, 112.5)
        events = fsm.process_exec_close(break_bar)
        self.assertEqual(fsm.state, SideState.WAIT_SIGNAL)
        self.assertTrue(any(event.type == "BREAK_CONFIRMED" for event in events))

        rc = candle(112.5, 113, 111.5, 111.8)
        events = fsm.process_exec_close(rc)
        self.assertEqual(fsm.state, SideState.PENDING)
        self.assertTrue(any(event.type == "ARM_PENDING" for event in events))
        self.assertAlmostEqual(fsm.entry, 111.49)
        self.assertAlmostEqual(fsm.stop_loss, 113.01)
        fsm.mark_pending_placed("order-1", 0.1)

        invalidate = candle(112, 114, 111.6, 113.5)  # close above RC.high
        events = fsm.process_exec_close(invalidate)
        self.assertEqual(fsm.state, SideState.WAIT_SIGNAL)
        self.assertTrue(any(event.type == "INVALIDATE_PENDING" for event in events))
        self.assertIsNone(fsm.pending_order_id)

    def test_master_level_from_single_candle_any_color(self):
        settings = MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 100}]})
        short = MasterBreakSideFSM(side="SHORT", settings=settings, point=0.01)
        red = candle(110, 111, 100, 101)
        events = short.process_master_close(red)
        self.assertEqual(short.state, SideState.WAIT_BREAK)
        self.assertEqual(short.level, 111)
        self.assertEqual(events[0].payload.get("kind"), "MASTER_HIGH")

        long = MasterBreakSideFSM(side="LONG", settings=settings, point=0.01)
        green = candle(101, 115, 100.5, 114)
        events = long.process_master_close(green)
        self.assertEqual(long.state, SideState.WAIT_BREAK)
        self.assertEqual(long.level, 100.5)
        self.assertEqual(events[0].payload.get("kind"), "MASTER_LOW")

    def test_new_master_replaces_level_while_waiting_break(self):
        settings = MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 100}]})
        fsm = MasterBreakSideFSM(side="SHORT", settings=settings, point=0.01)
        fsm.process_master_close(candle(100, 110, 99, 108))
        self.assertEqual(fsm.level, 110)
        fsm.process_master_close(candle(108, 112, 107, 111))
        self.assertEqual(fsm.state, SideState.WAIT_BREAK)
        self.assertEqual(fsm.level, 112)

    def test_long_mirrors_short(self):
        settings = MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 100}]})
        fsm = MasterBreakSideFSM(side="LONG", settings=settings, point=0.01)
        fsm.process_master_close(candle(106, 107, 100, 101))
        self.assertEqual(fsm.level, 100)
        fsm.process_exec_close(candle(101, 101.5, 99.5, 99.8))
        self.assertEqual(fsm.state, SideState.WAIT_SIGNAL)
        fsm.process_exec_close(candle(99.8, 100.5, 99.6, 100.2))
        self.assertEqual(fsm.state, SideState.PENDING)
        self.assertAlmostEqual(fsm.entry, 100.51)
        self.assertAlmostEqual(fsm.stop_loss, 99.59)


if __name__ == "__main__":
    unittest.main()
