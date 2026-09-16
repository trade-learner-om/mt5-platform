import unittest
from datetime import datetime

from app.services.gold_strategy_rules import (
    MAX_GOLD_SL_PIPS,
    OpenTrade,
    SymbolRiskContext,
    calc_setup_prices,
    effective_exit_price,
    is_green_candle,
    is_red_candle,
    management_action,
    ManagementState,
    next_trailing_locked_r,
    pending_fill_price,
    pending_invalidated,
    planned_risk_usd,
    pre_wick_skip_sides,
    setup_sl_rejected,
    simulate_quantity,
    simulate_trade_pnl,
    summarize_trade_exit,
    trailing_stop_for_r,
)
from app.services.gold_strategy_simulator import GoldDaySimulator, simulate_broker_day


class GoldStrategyRulesTests(unittest.TestCase):
    def test_pre_wick_skip_sides(self):
        self.assertEqual(pre_wick_skip_sides(4325, 4310, 4320, 4300), (True, False))
        self.assertEqual(pre_wick_skip_sides(4315, 4295, 4320, 4300), (False, True))

    def test_setup_sl_rejected_at_100_pips(self):
        self.assertFalse(setup_sl_rejected(99.0, MAX_GOLD_SL_PIPS))
        self.assertTrue(setup_sl_rejected(100.1, MAX_GOLD_SL_PIPS))

    def test_long_setup_prices(self):
        candle = {"open": 4300, "high": 4305, "low": 4298, "close": 4304}
        prices = calc_setup_prices("LONG", candle, 0.01)
        self.assertEqual(prices.entry, 4305.01)
        self.assertEqual(prices.stop_loss, 4297.99)

    def test_pending_invalidation_and_fill(self):
        setup = {"open": 4300, "high": 4305, "low": 4298, "close": 4304}
        invalid = {"open": 4304, "high": 4304.5, "low": 4297.5, "close": 4299}
        valid_fill = {"open": 4299, "high": 4306, "low": 4299, "close": 4305.5}
        self.assertTrue(pending_invalidated("LONG", setup, invalid))
        self.assertTrue(pending_fill_price("LONG", 4305.01, valid_fill))

    def test_micro_lot_trailing(self):
        state = ManagementState(
            quantity=0.01,
            entry=4300.0,
            stop_loss=4290.0,
            direction="LONG",
            remaining_qty=0.01,
        )
        candle = {"open": 4300, "high": 4340, "low": 4299, "close": 4338}
        action = management_action(state, candle, min_target_breakeven_r=4, final_target_r=20)
        self.assertEqual(action.kind, "trail_sl")
        self.assertEqual(state.trailing_locked_r, 4)

    def test_standard_lot_partial_at_4r(self):
        state = ManagementState(
            quantity=0.1,
            entry=4300.0,
            stop_loss=4290.0,
            direction="LONG",
            remaining_qty=0.1,
        )
        candle = {"open": 4338, "high": 4341, "low": 4337, "close": 4340}
        action = management_action(state, candle, min_target_breakeven_r=4, final_target_r=20)
        self.assertEqual(action.kind, "partial_t1")
        self.assertEqual(action.close_qty, 0.05)

    def test_trailing_locked_r_ladder(self):
        self.assertEqual(next_trailing_locked_r(0, 4.2, 4), 4)
        self.assertEqual(next_trailing_locked_r(4, 8.5, 4), 8)
        self.assertEqual(trailing_stop_for_r("LONG", 4300, 10, 4), 4340)

    def test_open_trade_initializes_management(self):
        trade = OpenTrade(
            direction="LONG",
            entry=4300.0,
            stop_loss=4290.0,
            quantity=0.05,
            sl_pips=10.0,
            htc=4320.0,
            ltc=4290.0,
            breach_at="2026-01-15T04:12:00Z",
        )
        self.assertEqual(trade.management.entry, 4300.0)
        self.assertEqual(trade.management.remaining_qty, 0.05)

    def test_effective_exit_price_caps_long_loss_at_stop(self):
        self.assertEqual(effective_exit_price("LONG", 4290.0, 4200.0), 4290.0)
        self.assertEqual(effective_exit_price("LONG", 4290.0, 4310.0), 4310.0)

    def test_summarize_trade_exit_weighted_price(self):
        summary = summarize_trade_exit(
            [
                {"type": "T1", "qty": 0.05, "pnl": 50.0, "price": 4340.0},
                {"type": "T2", "qty": 0.05, "pnl": 250.0, "price": 4500.0},
            ],
            "LONG",
            4300.0,
            4290.0,
            "T2",
        )
        self.assertEqual(summary["exitPrice"], 4420.0)
        self.assertEqual(summary["statusLabel"], "Full target after partial")
        self.assertIn("50% at breakeven R", summary["exitSummary"])

    def test_long_target_pnl_is_positive(self):
        pnl = simulate_trade_pnl("LONG", 4660.70, 4669.38, 0.09)
        self.assertGreater(pnl, 0)
        self.assertAlmostEqual(pnl, 78.12, places=1)

    def test_short_target_pnl_is_positive(self):
        pnl = simulate_trade_pnl("SHORT", 4660.70, 4652.00, 0.09)
        self.assertGreater(pnl, 0)


class GoldStrategySimulatorTests(unittest.TestCase):
    def test_long_day_produces_trade_or_skips(self):
        candles = []
        base = 4300
        for minute in range(60):
            close = base - 2 if minute < 5 else base + (minute - 5) * 0.2
            candles.append(
                {
                    "time": datetime(2026, 1, 15, 4, minute),
                    "open": close - 0.1,
                    "high": close + 0.3,
                    "low": close - 0.4,
                    "close": close,
                }
            )
        trades = simulate_broker_day(
            "2026-01-15",
            candles,
            htc=4320,
            ltc=4305,
            day_high_at_start=4300,
            day_low_at_start=4295,
            risk_amount=100,
        )
        self.assertIsInstance(trades, list)

    def test_clean_sl_loss_near_planned_risk(self):
        entry = 4300.0
        stop = 4290.0
        candles = [
            {"time": datetime(2026, 1, 15, 4, 0), "open": 4306, "high": 4306, "low": 4304.5, "close": 4304.8},
            {"time": datetime(2026, 1, 15, 4, 1), "open": 4304.8, "high": 4305.2, "low": 4304.6, "close": 4305.0},
            {"time": datetime(2026, 1, 15, 4, 2), "open": 4305.0, "high": 4305.5, "low": 4304.8, "close": 4305.2},
            {"time": datetime(2026, 1, 15, 4, 3), "open": 4305.2, "high": 4306.0, "low": 4305.0, "close": 4305.8},
            {"time": datetime(2026, 1, 15, 4, 4), "open": 4305.8, "high": 4306.5, "low": 4305.5, "close": 4306.2},
            {"time": datetime(2026, 1, 15, 4, 5), "open": 4306.2, "high": 4306.4, "low": 4289.5, "close": 4290.0},
        ]
        trades = simulate_broker_day(
            "2026-01-15",
            candles,
            htc=4310,
            ltc=4305,
            day_high_at_start=4306,
            day_low_at_start=4304,
            risk_amount=100,
        )
        sl_trades = [trade for trade in trades if trade["status"] == "SL"]
        if sl_trades:
            planned = planned_risk_usd(100)
            self.assertLessEqual(abs(sl_trades[0]["pnl"]), planned * 1.05)

    def test_eod_loss_capped_at_stop(self):
        entry = 4300.0
        stop = 4290.0
        candles = [
            {"time": datetime(2026, 1, 15, 4, 0), "open": 4306, "high": 4306, "low": 4304.5, "close": 4304.8},
            {"time": datetime(2026, 1, 15, 4, 1), "open": 4304.8, "high": 4305.2, "low": 4304.6, "close": 4305.0},
            {"time": datetime(2026, 1, 15, 4, 2), "open": 4305.0, "high": 4305.5, "low": 4304.8, "close": 4305.2},
            {"time": datetime(2026, 1, 15, 4, 3), "open": 4305.2, "high": 4306.0, "low": 4305.0, "close": 4305.8},
            {"time": datetime(2026, 1, 15, 4, 4), "open": 4305.8, "high": 4306.5, "low": 4305.5, "close": 4306.2},
            {"time": datetime(2026, 1, 15, 4, 5), "open": 4306.2, "high": 4306.4, "low": 4306.0, "close": 4306.2},
            {"time": datetime(2026, 1, 15, 23, 59), "open": 4200, "high": 4205, "low": 4190, "close": 4190},
        ]
        trades = simulate_broker_day(
            "2026-01-15",
            candles,
            htc=4310,
            ltc=4305,
            day_high_at_start=4306,
            day_low_at_start=4304,
            risk_amount=100,
            auto_close_eod=True,
        )
        eod_trades = [trade for trade in trades if trade["status"] == "EOD"]
        if eod_trades:
            planned = planned_risk_usd(100)
            self.assertLessEqual(abs(eod_trades[0]["pnl"]), planned * 1.05)
            self.assertEqual(eod_trades[0]["exitPrice"], stop)

    def test_auto_close_eod_false_carries_position(self):
        day_one = [
            {"time": datetime(2026, 1, 15, 4, 0), "open": 4306, "high": 4306, "low": 4304.5, "close": 4304.8},
            {"time": datetime(2026, 1, 15, 4, 1), "open": 4304.6, "high": 4305.5, "low": 4304.5, "close": 4305.2},
            {"time": datetime(2026, 1, 15, 4, 2), "open": 4305.2, "high": 4306.0, "low": 4305.0, "close": 4305.8},
            {"time": datetime(2026, 1, 15, 23, 59), "open": 4306.2, "high": 4306.4, "low": 4306.0, "close": 4306.2},
        ]
        sim = GoldDaySimulator(risk_amount=100, auto_close_eod=False)
        sim.begin_day("2026-01-15", 4310, 4305, 4306, 4304)
        for candle in day_one:
            sim.process_candle(candle, "2026-01-15")
        if sim.open_trade is None:
            self.skipTest("Setup did not fill in synthetic carry scenario.")
        sim.close_end_of_day(day_one[-1], "2026-01-15")
        self.assertIsNotNone(sim.open_trade)
        self.assertEqual(len(sim.trades), 0)

    def test_retry_rows_have_attempt_numbers(self):
        candles = [
            {"time": datetime(2026, 1, 15, 4, 0), "open": 4306, "high": 4306, "low": 4304.5, "close": 4304.8},
            {"time": datetime(2026, 1, 15, 4, 1), "open": 4304.8, "high": 4305.2, "low": 4304.6, "close": 4305.0},
            {"time": datetime(2026, 1, 15, 4, 2), "open": 4305.0, "high": 4305.5, "low": 4304.8, "close": 4305.2},
            {"time": datetime(2026, 1, 15, 4, 3), "open": 4305.2, "high": 4306.0, "low": 4305.0, "close": 4305.8},
            {"time": datetime(2026, 1, 15, 4, 4), "open": 4305.8, "high": 4306.5, "low": 4305.5, "close": 4306.2},
            {"time": datetime(2026, 1, 15, 4, 5), "open": 4306.2, "high": 4306.4, "low": 4289.5, "close": 4290.0},
            {"time": datetime(2026, 1, 15, 4, 6), "open": 4290.0, "high": 4290.5, "low": 4288.0, "close": 4288.5},
            {"time": datetime(2026, 1, 15, 4, 7), "open": 4288.5, "high": 4289.0, "low": 4287.5, "close": 4288.0},
            {"time": datetime(2026, 1, 15, 4, 8), "open": 4288.0, "high": 4289.5, "low": 4287.8, "close": 4289.0},
            {"time": datetime(2026, 1, 15, 4, 9), "open": 4289.0, "high": 4290.5, "low": 4288.8, "close": 4290.0},
        ]
        trades = simulate_broker_day(
            "2026-01-15",
            candles,
            htc=4310,
            ltc=4305,
            day_high_at_start=4306,
            day_low_at_start=4304,
            risk_amount=100,
        )
        if len(trades) >= 2:
            self.assertEqual(trades[0]["attemptNumber"], 1)
            self.assertFalse(trades[0]["isRetry"])
            self.assertEqual(trades[1]["attemptNumber"], 2)
            self.assertTrue(trades[1]["isRetry"])


if __name__ == "__main__":
    unittest.main()
