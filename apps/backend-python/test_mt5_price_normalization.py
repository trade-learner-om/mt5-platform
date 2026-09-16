import unittest

from app.services.risk import digits_from_symbol_spec, normalize_price_to_symbol


class MT5PriceNormalizationTests(unittest.TestCase):
    def test_digits_from_symbol_spec(self):
        self.assertEqual(digits_from_symbol_spec({"digits": 2, "tickSize": 0.01}), 2)
        self.assertEqual(digits_from_symbol_spec({"tickSize": 0.001}), 3)
        self.assertEqual(digits_from_symbol_spec({}), 5)

    def test_eurusd_snaps_extra_precision_to_tick_grid(self):
        spec = {"digits": 5, "tickSize": 0.00001, "point": 0.00001}
        self.assertEqual(normalize_price_to_symbol(1.123456789, spec), 1.12346)

    def test_xauusd_snaps_to_two_decimal_tick(self):
        spec = {"digits": 2, "tickSize": 0.01, "point": 0.01}
        self.assertEqual(normalize_price_to_symbol(2650.005, spec), 2650.01)
        self.assertEqual(normalize_price_to_symbol(2645.123, spec), 2645.12)

    def test_zero_or_negative_prices_are_preserved(self):
        spec = {"digits": 2, "tickSize": 0.01, "point": 0.01}
        self.assertEqual(normalize_price_to_symbol(0, spec), 0.0)
        self.assertEqual(normalize_price_to_symbol(-1, spec), -1.0)

    def test_uses_digits_when_tick_size_missing(self):
        spec = {"digits": 3}
        self.assertEqual(normalize_price_to_symbol(1.23456, spec), 1.235)


if __name__ == "__main__":
    unittest.main()
