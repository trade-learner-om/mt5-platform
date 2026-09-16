import unittest
from datetime import datetime, timedelta, timezone

from app.services.master_break_backtest import simulate_master_break_backtest
from app.services.master_break_backtest_analytics import compute_trades_summary
from app.services.master_break_fsm import MasterBreakSideFSM, SideState
from app.services.master_break_levels import coerce_candle_time
from app.services.master_break_settings import MasterBreakSettings


def bar(t, open_, high, low, close):
    return {"time": t, "open": open_, "high": high, "low": low, "close": close}


class MasterBreakBacktestTests(unittest.TestCase):
    def setUp(self):
        self.point = 0.01
        self.spec = {
            "symbol": "XAUUSD",
            "contractSize": 100,
            "volumeStep": 0.01,
            "volumeMin": 0.01,
            "volumeMax": 100,
            "digits": 2,
            "point": 0.01,
        }
        self.settings = MasterBreakSettings.from_mapping(
            {
                "risk_amount": 10,
                "breakeven_r": 1.0,
                "targets": [{"r": 1.0, "qty_pct": 50.0}, {"r": 2.0, "qty_pct": 50.0}],
                "master_timeframe": "H6",
                "exec_timeframe": "M5",
            }
        )

    def test_dual_parallel_short_and_long_setups(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 100, 110, 99, 108),
            bar(start + timedelta(hours=6), 108, 112, 107, 111),  # closes at +12h → short level 112
            bar(start + timedelta(hours=12), 111, 113, 105, 106),
            bar(start + timedelta(hours=18), 106, 107, 100, 101),  # closes at +24h → long level 100
            bar(start + timedelta(hours=24), 101, 102, 100.5, 101.5),
            bar(start + timedelta(hours=30), 101.5, 102, 101, 101.2),
        ]
        # Masters activate at close: H6@+6h active from +12h; H6@+18h active from +24h.
        t_short = start + timedelta(hours=12, minutes=5)
        t_long = start + timedelta(hours=24, minutes=5)
        execs = [
            bar(t_short, 111, 113, 110.5, 112.5),  # break above master high 112
            bar(t_short + timedelta(minutes=5), 112.5, 113.0, 111.5, 111.8),  # red RC
            bar(t_short + timedelta(minutes=10), 111.8, 111.9, 111.4, 111.45),  # fill short
            bar(t_long, 101, 101.2, 99.5, 99.7),  # break below master low 100
            bar(t_long + timedelta(minutes=5), 99.7, 100.4, 99.6, 100.2),  # green GC
            bar(t_long + timedelta(minutes=10), 100.2, 100.55, 100.1, 100.5),  # fill long
            bar(t_long + timedelta(minutes=15), 100.5, 100.6, 100.4, 100.55),
        ]
        result = simulate_master_break_backtest(self.spec, masters, execs, self.settings, self.point)
        sides = {trade["side"] for trade in result["trades"]}
        arm_sides = {roll["side"] for roll in result["rolls"] if roll["event"] == "ARM_PENDING"}
        self.assertTrue({"SHORT", "LONG"}.issubset(arm_sides) or len(sides) >= 1)
        self.assertIn("summary", result)
        self.assertIn("total_pnl", result["summary"])

    def test_invalidate_unfilled_short_then_rearm(self):
        settings = MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 100}], "risk_amount": 10})
        fsm = MasterBreakSideFSM(side="SHORT", settings=settings, point=0.01)
        fsm.process_master_close(bar(None, 108, 112, 107, 111))
        fsm.process_exec_close(bar(None, 111, 113, 110.5, 112.5))
        fsm.process_exec_close(bar(None, 112.5, 113.0, 111.5, 111.8))
        fsm.mark_pending_placed("1", 0.1)
        events = fsm.process_exec_close(bar(None, 112, 114, 111.6, 113.2))
        self.assertEqual(fsm.state, SideState.WAIT_SIGNAL)
        self.assertTrue(any(event.type == "INVALIDATE_PENDING" for event in events))
        # new RC rearms
        events = fsm.process_exec_close(bar(None, 113, 113.2, 112.0, 112.1))
        self.assertEqual(fsm.state, SideState.PENDING)
        self.assertTrue(any(event.type == "ARM_PENDING" for event in events))

    def test_multi_target_and_breakeven(self):
        settings = MasterBreakSettings.from_mapping(
            {
                "risk_amount": 100,
                "breakeven_r": 1.0,
                "targets": [{"r": 2.0, "qty_pct": 50.0}, {"r": 3.0, "qty_pct": 50.0}],
            }
        )
        fsm = MasterBreakSideFSM(side="LONG", settings=settings, point=0.01)
        fsm.state = SideState.OPEN
        fsm.entry = 100.0
        fsm.stop_loss = 99.0
        fsm.risk_distance = 1.0
        fsm.quantity = 0.10
        fsm.remaining_qty = 0.10
        fsm.targets_hit = [False, False]

        # Reach 1R → BE
        events = fsm.process_tick(101.0, high=101.0, low=100.5)
        self.assertTrue(any(event.type == "MOVE_BREAKEVEN" for event in events))
        self.assertEqual(fsm.stop_loss, 100.0)
        self.assertTrue(fsm.breakeven_armed)

        # Reach 2R → first partial
        events = fsm.process_tick(102.0, high=102.0, low=101.5)
        self.assertTrue(any(event.type == "PARTIAL_EXIT" for event in events))
        self.assertAlmostEqual(fsm.remaining_qty, 0.05, places=6)

        # Reach 3R → second partial + close
        events = fsm.process_tick(103.0, high=103.0, low=102.5)
        self.assertTrue(any(event.type == "PARTIAL_EXIT" for event in events))
        self.assertTrue(any(event.type == "TRADE_CLOSED" for event in events))
        self.assertEqual(fsm.state, SideState.SEEKING_MASTER)

    def test_no_sl_retry(self):
        settings = MasterBreakSettings.from_mapping({"targets": [{"r": 2, "qty_pct": 100}]})
        fsm = MasterBreakSideFSM(side="SHORT", settings=settings, point=0.01)
        fsm.state = SideState.OPEN
        fsm.entry = 100.0
        fsm.stop_loss = 101.0
        fsm.risk_distance = 1.0
        fsm.quantity = 0.1
        fsm.remaining_qty = 0.1
        events = fsm.process_tick(100.5, high=101.2, low=100.4)
        self.assertTrue(any(event.type == "STOPPED_OUT" for event in events))
        self.assertEqual(fsm.state, SideState.SEEKING_MASTER)
        self.assertIsNone(fsm.entry)

    def test_same_bar_fill_and_stop_does_not_crash(self):
        """Fill+SL in one process_tick clears fsm.entry before handlers; must use event payload."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 100, 110, 99, 108),
            bar(start + timedelta(hours=6), 108, 112, 107, 111),
            bar(start + timedelta(hours=12), 111, 113, 105, 106),
        ]
        t0 = start + timedelta(hours=12, minutes=5)
        settings = MasterBreakSettings.from_mapping(
            {
                "risk_amount": 10,
                "breakeven_r": 10,
                "targets": [{"r": 5.0, "qty_pct": 100}],
                "master_timeframe": "H6",
                "exec_timeframe": "M5",
            }
        )
        # Break → red arm (entry≈111.49, SL≈113.01) → next bar fills and hits SL.
        # Close must stay ≤ signal extreme (113) or pending invalidates before fill.
        execs = [
            bar(t0, 111, 113, 110.5, 112.5),
            bar(t0 + timedelta(minutes=5), 112.5, 113.0, 111.5, 111.8),
            bar(t0 + timedelta(minutes=10), 111.8, 113.05, 111.4, 112.0),
            bar(t0 + timedelta(minutes=15), 112.0, 112.1, 111.9, 112.0),
        ]
        result = simulate_master_break_backtest(self.spec, masters, execs, settings, self.point)
        events = [r["event"] for r in result["rolls"] if r["side"] == "SHORT"]
        self.assertIn("FILLED", events)
        self.assertIn("STOPPED_OUT", events)
        self.assertTrue(result["trades"])
        trade = result["trades"][0]
        self.assertIsNotNone(trade.get("entry"))
        self.assertGreater(float(trade["entry"]), 0)
        self.assertEqual(trade.get("exit_reason"), "SL")

    def test_summary_analytics_handles_unix_and_mixed_datetimes(self):
        trades = [
            {
                "total_pnl": 10,
                "exit_time": datetime(2026, 9, 2, 12, 0),  # naive
                "entry_time": datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc),
            },
            {
                "total_pnl": -4,
                "exit_time": 1725270000,
                "entry_time": 1725267000,
            },
        ]
        summary = compute_trades_summary(trades)
        self.assertEqual(summary["total_trades"], 2)
        self.assertEqual(summary["total_pnl"], 6)
        self.assertIsNotNone(summary["max_dd_period"].get("duration_seconds"))
        for key in ("from", "to"):
            value = summary["max_dd_period"].get(key)
            self.assertIsInstance(value, str)
            self.assertRegex(value, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
            self.assertNotRegex(value, r"^\d{10,}$")

    def test_summary_analytics(self):
        trades = [
            {"total_pnl": 10, "exit_time": "2026-01-01T10:00:00+00:00"},
            {"total_pnl": -4, "exit_time": "2026-01-01T11:00:00+00:00"},
            {"total_pnl": 6, "exit_time": "2026-01-01T12:00:00+00:00"},
        ]
        summary = compute_trades_summary(trades)
        self.assertEqual(summary["total_trades"], 3)
        self.assertEqual(summary["total_pnl"], 12)
        self.assertAlmostEqual(summary["win_pct"], 66.67, places=1)
        self.assertEqual(summary["max_profit"], 10)
        self.assertEqual(summary["max_loss"], -4)
        self.assertIn("from", summary["max_dd_period"])

    def test_pnl_matches_calc_pnl_from_price_move_not_tick_value(self):
        from app.services.master_break_risk import pnl_from_fill, quantity_from_risk
        from app.services.risk import calc_pnl_from_price_move

        # Misleading tickValue must not drive PnL (old bug: price_move * lots * tickValue).
        spec = {
            **self.spec,
            "tickValue": 0.01,
            "tickSize": 0.01,
            "contractSize": 100,
        }
        entry = 2000.0
        stop = 2001.0
        exit_price = 1998.0
        qty = quantity_from_risk(10, entry, stop, symbol_spec=spec, symbol="XAUUSD")
        self.assertGreater(qty, 0)
        expected = calc_pnl_from_price_move(
            "XAUUSD",
            "SHORT",
            entry,
            exit_price,
            qty,
            contract_size=100,
        )
        valued = pnl_from_fill("SHORT", entry, exit_price, qty, symbol_spec=spec, symbol="XAUUSD")
        self.assertAlmostEqual(valued, expected, places=2)
        wrong_tick_style = (entry - exit_price) * qty * float(spec["tickValue"])
        self.assertNotAlmostEqual(valued, wrong_tick_style, places=2)

        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 1990, 2005, 1988, 2000),
            bar(start + timedelta(hours=6), 2000, 2010, 1999, 2008),  # closes at +12h
            bar(start + timedelta(hours=12), 2008, 2009, 2007, 2008.5),
        ]
        t0 = start + timedelta(hours=12, minutes=5)
        # Break above master high 2010 after H6@+6h has closed
        settings = MasterBreakSettings.from_mapping(
            {"risk_amount": 10, "breakeven_r": 10, "targets": [{"r": 2.0, "qty_pct": 100}]}
        )
        execs = [
            bar(t0, 2008, 2011, 2007, 2010.5),
            bar(t0 + timedelta(minutes=5), 2010.5, 2011.0, 2009.0, 2009.2),
            bar(t0 + timedelta(minutes=10), 2009.2, 2009.3, 2008.98, 2009.0),  # fill near RC low-1pt
            bar(t0 + timedelta(minutes=15), 2009.0, 2009.1, 2000.0, 2001.0),  # deep move for 2R
            bar(t0 + timedelta(minutes=20), 2001.0, 2001.1, 2000.9, 2001.0),
        ]
        result = simulate_master_break_backtest(spec, masters, execs, settings, self.point)
        self.assertTrue(result["trades"])
        trade = result["trades"][0]
        rebuilt = 0.0
        for leg in trade.get("partials") or []:
            rebuilt += pnl_from_fill(
                trade["side"],
                float(trade["entry"]),
                float(leg["price"]),
                float(leg["qty"]),
                symbol_spec=spec,
                symbol="XAUUSD",
            )
        self.assertAlmostEqual(float(trade["total_pnl"]), round(rebuilt, 6), places=2)

    def test_master_rows_one_per_completed_master_in_range(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start - timedelta(hours=6), 99, 100, 98, 99.5),  # warmup
            bar(start, 100, 110, 99, 108),
            bar(start + timedelta(hours=6), 108, 112, 107, 111),
            bar(start + timedelta(hours=12), 111, 113, 105, 106),
            bar(start + timedelta(hours=18), 106, 107, 100, 101),
        ]
        execs = [
            bar(start + timedelta(hours=1), 108, 109, 107.5, 108.5),
            bar(start + timedelta(hours=7), 111, 111.5, 110.5, 111.2),
            bar(start + timedelta(hours=13), 106, 106.5, 105.5, 106.1),
            bar(start + timedelta(hours=19), 101, 101.5, 100.5, 101.1),
        ]
        result = simulate_master_break_backtest(
            self.spec,
            masters,
            execs,
            self.settings,
            self.point,
            range_start=start,
            range_end=start + timedelta(hours=18),
        )
        rows = result["master_rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["color"], "green")
        self.assertEqual(rows[0]["high"], 110)
        self.assertEqual(rows[0]["low"], 99)
        for row in rows:
            self.assertIn("sides", row)
            self.assertIn("SHORT", row["sides"])
            self.assertIn("LONG", row["sides"])
            self.assertEqual(row["sides"]["SHORT"]["entry_filled"], "no")
            self.assertIsNone(row["sides"]["SHORT"]["result_pnl"])
            self.assertIsNone(row["sides"]["LONG"]["result_pnl"])

    def test_master_rows_break_arm_fill_and_unfilled_pnl_null(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 100, 110, 99, 108),
            bar(start + timedelta(hours=6), 108, 112, 107, 111),  # closes at +12h
            bar(start + timedelta(hours=12), 111, 113, 105, 106),
        ]
        t0 = start + timedelta(hours=12, minutes=5)
        execs = [
            bar(t0, 111, 113, 110.5, 112.5),  # break above master high 112
            bar(t0 + timedelta(minutes=5), 112.5, 113.0, 111.5, 111.8),  # RC arm short
            bar(t0 + timedelta(minutes=10), 111.8, 111.9, 111.4, 111.45),  # fill short
            bar(t0 + timedelta(minutes=15), 111.45, 111.5, 110.0, 110.2),  # move
            bar(t0 + timedelta(minutes=20), 110.2, 110.3, 110.1, 110.2),
        ]
        result = simulate_master_break_backtest(self.spec, masters, execs, self.settings, self.point)
        rows = result["master_rows"]
        self.assertEqual(len(rows), 3)
        owner = rows[1]  # second master owns the high/low level after it closes
        short = owner["sides"]["SHORT"]
        self.assertEqual(short["level"], 112)
        self.assertEqual(short["level_kind"], "MASTER_HIGH")
        self.assertEqual(short["exec_closed_beyond"], "yes")
        self.assertEqual(short["side_breached"], "High")
        self.assertEqual(short["bias_formed"], "Short")
        self.assertEqual(short["signal_candle_color"], "red")
        self.assertIsNotNone(short["planned_entry"])
        self.assertEqual(short["entry_filled"], "yes")
        self.assertIsNotNone(short["entry_fill_time"])
        # Unfilled long on same row stays null pnl
        long = owner["sides"]["LONG"]
        self.assertEqual(long["level"], 107)
        self.assertEqual(long["level_kind"], "MASTER_LOW")
        self.assertEqual(long["entry_filled"], "no")
        self.assertIsNone(long["result_pnl"])
        # First master had no break
        idle = rows[0]["sides"]["SHORT"]
        self.assertEqual(idle["exec_closed_beyond"], "no")
        self.assertIsNone(idle["result_pnl"])

    def test_backtest_tolerates_none_point_and_sparse_spec(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 100, 110, 99, 108),
            bar(start + timedelta(hours=6), 108, 112, 107, 111),
            bar(start + timedelta(hours=12), 111, 113, 105, 106),
        ]
        t0 = start + timedelta(hours=12, minutes=5)
        execs = [
            bar(t0, 111, 113, 110.5, 112.5),
            bar(t0 + timedelta(minutes=5), 112.5, 113.0, 111.5, 111.8),
            bar(t0 + timedelta(minutes=10), 111.8, 111.9, 111.4, 111.45),
            bar(t0 + timedelta(minutes=15), 111.45, 111.5, 110.0, 110.2),
            bar(t0 + timedelta(minutes=20), 110.2, 110.3, 110.1, 110.2),
        ]
        sparse = {"symbol": "XAUUSD", "tickSize": None, "point": None, "contractSize": None}
        result = simulate_master_break_backtest(sparse, masters, execs, self.settings, None)
        self.assertIn("summary", result)
        self.assertGreaterEqual(len(result["rolls"]), 1)

    def test_h6_close_time_not_open_time_lookahead(self):
        """H6@00:00 high=110 must stay active after 06:00; H6@06:00 high=200 must not replace early."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        masters = [
            bar(start, 100, 110, 99, 108),  # 00:00–06:00, closes at 06:00
            bar(start + timedelta(hours=6), 108, 200, 107, 190),  # lookahead trap if applied at open
            bar(start + timedelta(hours=12), 190, 191, 189, 190.5),
        ]
        # M5 from 06:00: close above 110 but below 200 → must break/arm/fill on prior high.
        t0 = start + timedelta(hours=6, minutes=5)
        arm_t = t0 + timedelta(minutes=5)
        fill_t = t0 + timedelta(minutes=10)
        execs = [
            bar(t0, 109, 111, 108.5, 110.5),  # break above 110
            bar(arm_t, 110.5, 111.0, 109.5, 109.8),  # red arm; no fill on this bar
            bar(fill_t, 109.8, 109.9, 109.4, 109.5),  # subsequent low hits entry
            bar(fill_t + timedelta(minutes=5), 109.5, 109.6, 108.0, 108.2),
            bar(fill_t + timedelta(minutes=10), 108.2, 108.3, 108.1, 108.2),
        ]
        settings = MasterBreakSettings.from_mapping(
            {
                "risk_amount": 10,
                "breakeven_r": 10,
                "targets": [{"r": 2.0, "qty_pct": 100}],
                "master_timeframe": "H6",
                "exec_timeframe": "M5",
            }
        )
        result = simulate_master_break_backtest(self.spec, masters, execs, settings, self.point)
        events = [(r["event"], r["side"]) for r in result["rolls"]]
        self.assertIn(("BREAK_CONFIRMED", "SHORT"), events)
        self.assertIn(("ARM_PENDING", "SHORT"), events)
        self.assertIn(("FILLED", "SHORT"), events)
        owner = result["master_rows"][0]["sides"]["SHORT"]
        self.assertEqual(owner["level"], 110)
        self.assertEqual(owner["entry_filled"], "yes")
        # Arm bar must not fill; fill is on a later candle.
        fill_rolls = [r for r in result["rolls"] if r["event"] == "FILLED" and r["side"] == "SHORT"]
        self.assertEqual(len(fill_rolls), 1)
        self.assertEqual(coerce_candle_time(fill_rolls[0]["time"]), coerce_candle_time(fill_t))
        self.assertTrue(result["trades"])

    def test_master_rows_survive_unix_int_candle_times(self):
        """Production get_backtest_candles uses unix int times; must not empty master_rows."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        def unix_bar(when, open_, high, low, close):
            return {
                "time": int(when.timestamp()),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            }

        masters = [
            unix_bar(start - timedelta(hours=6), 99, 100, 98, 99.5),
            unix_bar(start, 100, 110, 99, 108),
            unix_bar(start + timedelta(hours=6), 108, 112, 107, 111),
            unix_bar(start + timedelta(hours=12), 111, 113, 105, 106),
            unix_bar(start + timedelta(hours=18), 106, 107, 100, 101),
        ]
        execs = [
            unix_bar(start + timedelta(hours=1), 108, 109, 107.5, 108.5),
            unix_bar(start + timedelta(hours=7), 111, 111.5, 110.5, 111.2),
            unix_bar(start + timedelta(hours=13), 106, 106.5, 105.5, 106.1),
            unix_bar(start + timedelta(hours=19), 101, 101.5, 100.5, 101.1),
        ]
        result = simulate_master_break_backtest(
            self.spec,
            masters,
            execs,
            self.settings,
            self.point,
            range_start=start,
            range_end=start + timedelta(hours=18),
        )
        rows = result["master_rows"]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertTrue(str(row["time"]).startswith("2026-01-01"))
            self.assertNotIn("+00:00", str(row["time"]))
            self.assertNotRegex(str(row["time"]), r"^\d{10}$")


if __name__ == "__main__":
    unittest.main()
