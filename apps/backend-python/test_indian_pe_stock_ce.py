"""Tests for Indian PE→Stock→CE cycle contracts and backtest FSM."""

from __future__ import annotations

import unittest
from datetime import date

from app.services.indian_fno_contracts import (
    fno_equity_underlyings,
    parse_expiry_date,
    pick_equity,
    pick_monthly_ce,
    pick_monthly_pe,
    strike_near,
)
from app.services.indian_pe_stock_ce_backtest import simulate_pe_stock_ce_backtest
from app.services.mstock_client import MstockClient


def _last_thursday(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    day = next_month.fromordinal(next_month.toordinal() - 1)
    while day.weekday() != 3:
        day = day.fromordinal(day.toordinal() - 1)
    return day


class IndianFnoContractTests(unittest.TestCase):
    def test_strike_near(self):
        self.assertEqual(strike_near(95.0, [90, 100, 110]), 90.0)
        self.assertEqual(strike_near(108.0, [90, 100, 110]), 110.0)

    def test_parse_expiry_date(self):
        self.assertEqual(parse_expiry_date("2026-07-30"), date(2026, 7, 30))
        self.assertEqual(parse_expiry_date("30-JUL-2026"), date(2026, 7, 30))

    def test_pick_monthly_pe_ce_and_equity(self):
        expiry = _last_thursday(2026, 7)
        catalog = [
            {
                "symbol": "RELIANCE",
                "display_name": "Reliance",
                "exchange": "NSE",
                "instrument_token": 1,
                "instrument_type": "EQUITY",
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
            {
                "symbol": f"RELIANCE{expiry.strftime('%d%b%Y').upper()}900PE",
                "exchange": "NFO",
                "instrument_token": 2,
                "instrument_type": "OPTION",
                "option_type": "PE",
                "strike": 900.0,
                "expiry": expiry.isoformat(),
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
            {
                "symbol": f"RELIANCE{expiry.strftime('%d%b%Y').upper()}1100CE",
                "exchange": "NFO",
                "instrument_token": 3,
                "instrument_type": "OPTION",
                "option_type": "CE",
                "strike": 1100.0,
                "expiry": expiry.isoformat(),
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
            {
                "symbol": "RELIANCE26JULFUT",
                "exchange": "NFO",
                "instrument_token": 4,
                "instrument_type": "FUTURE",
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
        ]
        self.assertIn("RELIANCE", fno_equity_underlyings(catalog))
        equity = pick_equity(catalog, "RELIANCE")
        self.assertEqual(equity["symbol"], "RELIANCE")
        pe = pick_monthly_pe(catalog, "RELIANCE", date(2026, 7, 1), 1000.0)
        ce = pick_monthly_ce(catalog, "RELIANCE", date(2026, 7, 1), 1000.0)
        self.assertEqual(pe["strike"], 900.0)
        self.assertEqual(ce["strike"], 1100.0)


class IndianPeStockCeBacktestTests(unittest.TestCase):
    def test_cycle_pe_hit_then_ce_itm_restart(self):
        expiry = _last_thursday(2026, 7)
        pe_symbol = f"RELIANCE{expiry.strftime('%d%b%Y').upper()}900PE"
        ce_symbol = f"RELIANCE{expiry.strftime('%d%b%Y').upper()}1100CE"
        catalog = [
            {
                "symbol": "RELIANCE",
                "display_name": "Reliance",
                "exchange": "NSE",
                "instrument_token": 1,
                "instrument_type": "EQUITY",
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
            {
                "symbol": pe_symbol,
                "exchange": "NFO",
                "instrument_token": 2,
                "instrument_type": "OPTION",
                "option_type": "PE",
                "strike": 900.0,
                "expiry": expiry.isoformat(),
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
            {
                "symbol": ce_symbol,
                "exchange": "NFO",
                "instrument_token": 3,
                "instrument_type": "OPTION",
                "option_type": "CE",
                "strike": 1100.0,
                "expiry": expiry.isoformat(),
                "underlying": "RELIANCE",
                "lot_size": 250,
            },
        ]

        spot = {
            "2026-07-01": {"time": "2026-07-01", "open": 1000, "high": 1010, "low": 990, "close": 1000},
            "2026-07-02": {"time": "2026-07-02", "open": 980, "high": 985, "low": 890, "close": 895},
            expiry.isoformat(): {
                "time": expiry.isoformat(),
                "open": 1110,
                "high": 1120,
                "low": 1105,
                "close": 1115,
            },
        }
        pe_bars = {
            "2026-07-01": {"time": "2026-07-01", "open": 20, "high": 22, "low": 18, "close": 20},
            "2026-07-02": {"time": "2026-07-02", "open": 40, "high": 55, "low": 35, "close": 50},
        }
        ce_bars = {
            "2026-07-02": {"time": "2026-07-02", "open": 15, "high": 16, "low": 14, "close": 15},
            expiry.isoformat(): {"time": expiry.isoformat(), "open": 20, "high": 25, "low": 18, "close": 22},
        }

        def load_candles(instrument, from_date, to_date):
            symbol = instrument["symbol"]
            if symbol == "RELIANCE":
                return list(spot.values())
            if symbol == pe_symbol:
                return list(pe_bars.values())
            if symbol == ce_symbol:
                return list(ce_bars.values())
            return []

        result = simulate_pe_stock_ce_backtest(
            catalog=catalog,
            underlying="RELIANCE",
            from_date="2026-07-01",
            to_date=expiry.isoformat(),
            load_candles=load_candles,
        )
        types = [event["event_type"] for event in result["events"]]
        self.assertIn("PE_SOLD", types)
        self.assertIn("PE_HIT_SQUARE", types)
        self.assertIn("STOCK_BOUGHT", types)
        self.assertIn("CE_SOLD", types)
        self.assertIn("EXPIRY_ITM_FLAT", types)

    def test_normalize_historical_candles_list_rows(self):
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-07-01", 100, 110, 90, 105],
                    {"time": "2026-07-02", "open": 105, "high": 108, "low": 100, "close": 102},
                ]
            },
        }
        candles = MstockClient._normalize_historical_candles(payload)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["close"], 105.0)
        self.assertEqual(candles[1]["close"], 102.0)


if __name__ == "__main__":
    unittest.main()
