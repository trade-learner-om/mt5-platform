import unittest

from fastapi import HTTPException

from app.services.symbol_resolver import (
    CANONICAL_GOLD,
    build_auto_detect_aliases,
    infer_canonical,
    resolve_broker_symbol,
    suggest_symbols,
)


class SymbolResolverTests(unittest.TestCase):
    def test_infer_canonical_maps_gold_variants(self):
        self.assertEqual(infer_canonical("XAUUSD"), CANONICAL_GOLD)
        self.assertEqual(infer_canonical("XAUUSD+"), CANONICAL_GOLD)
        self.assertEqual(infer_canonical("EURUSD"), "EURUSD")

    def test_resolve_gold_on_vantage_style_list(self):
        available = ["EURUSD", "XAUUSD+", "GBPUSD"]
        resolved = resolve_broker_symbol("XAUUSD", available)
        self.assertEqual(resolved, "XAUUSD+")

    def test_vantage_xauusd_tv_exact_match(self):
        available = ["EURUSD", "XAUUSD.TV", "GBPUSD"]
        resolved = resolve_broker_symbol("XAUUSD.TV", available)
        self.assertEqual(resolved, "XAUUSD.TV")

    def test_vantage_xauusd_tv_heuristic(self):
        available = ["EURUSD", "XAUUSD.TV", "GBPUSD"]
        resolved = resolve_broker_symbol("XAUUSD", available)
        self.assertEqual(resolved, "XAUUSD.TV")

    def test_exact_broker_symbol_beats_gold_alias(self):
        available = ["XAUUSD", "XAUUSD.TV"]
        account = {"symbol_aliases": {"GOLD": "XAUUSD"}}
        resolved = resolve_broker_symbol("XAUUSD.TV", available, account)
        self.assertEqual(resolved, "XAUUSD.TV")

    def test_account_alias_override_beats_heuristic(self):
        available = ["XAUUSD+", "GOLD"]
        account = {"symbol_aliases": {"GOLD": "GOLD"}}
        resolved = resolve_broker_symbol("XAUUSD", available, account)
        self.assertEqual(resolved, "GOLD")

    def test_forex_suffix_matching(self):
        available = ["EURUSDm", "GBPUSD"]
        resolved = resolve_broker_symbol("EURUSD", available)
        self.assertEqual(resolved, "EURUSDm")

    def test_exact_match_passthrough(self):
        available = ["BTCUSD", "ETHUSD"]
        resolved = resolve_broker_symbol("BTCUSD", available)
        self.assertEqual(resolved, "BTCUSD")

    def test_missing_symbol_raises_with_suggestions(self):
        available = ["EURUSD", "XAUUSD+", "XAUUSDm"]
        with self.assertRaises(HTTPException) as ctx:
            resolve_broker_symbol("XAUUSD", ["EURUSD"])
        self.assertIn("No GOLD/XAUUSD symbol", str(ctx.exception.detail))

    def test_build_auto_detect_aliases(self):
        aliases = build_auto_detect_aliases(["EURUSDm", "XAUUSD+", "GBPUSD"])
        self.assertEqual(aliases["GOLD"], "XAUUSD+")
        self.assertEqual(aliases["EURUSD"], "EURUSDm")
        vantage_aliases = build_auto_detect_aliases(["EURUSD", "XAUUSD.TV", "GBPUSD"])
        self.assertEqual(vantage_aliases["GOLD"], "XAUUSD.TV")

    def test_suggest_symbols(self):
        available = ["XAUUSD+", "XAUUSDm", "EURUSD"]
        self.assertEqual(suggest_symbols("XAU", available), ["XAUUSD+", "XAUUSDm"])


if __name__ == "__main__":
    unittest.main()
