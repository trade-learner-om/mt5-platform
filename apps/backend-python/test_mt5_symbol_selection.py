import unittest

from app.services.mt5_symbol_utils import match_available_symbol_name, mt5_symbol_candidates


class MT5SymbolSelectionTests(unittest.TestCase):
    def test_candidates_include_requested_and_case_variants(self):
        self.assertEqual(mt5_symbol_candidates("XAUUSD.TV"), ["XAUUSD.TV", "xauusd.tv"])

    def test_normalized_lookup_matches_vantage_suffix_casing(self):
        available = ["EURUSD", "XAUUSD.tv", "GBPUSD"]
        matched = match_available_symbol_name("XAUUSD.TV", available)
        self.assertEqual(matched, "XAUUSD.tv")

    def test_lookup_live_price_is_case_insensitive(self):
        from app.services.symbol_resolver import lookup_live_price

        live_prices = {"XAUUSD.TV": {"bid": 4107.1, "ask": 4107.3}}
        tick = lookup_live_price(live_prices, "XAUUSD.tv")
        self.assertEqual(tick.get("bid"), 4107.1)


if __name__ == "__main__":
    unittest.main()
