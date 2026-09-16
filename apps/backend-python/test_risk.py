import unittest

from app.services.risk import (
    calc_quantity,
    calc_quantity_from_live_pip_value,
    calc_sl_pips,
    symbol_uses_pips,
)


class RiskSizingTests(unittest.TestCase):
    def test_forex_symbols_keep_pip_based_distance(self):
        self.assertTrue(symbol_uses_pips("EURUSD"))
        self.assertEqual(calc_sl_pips("EURUSD", 1.1050, 1.1000), 50.0)

    def test_crypto_symbols_use_raw_price_distance(self):
        self.assertFalse(symbol_uses_pips("BTCUSD"))
        self.assertEqual(calc_sl_pips("BTCUSD", 65000.0, 64500.0), 500.0)

    def test_crypto_quantity_uses_live_price_difference_not_pips(self):
        quantity = calc_quantity_from_live_pip_value(
            "BTCUSD",
            risk_amount=100.0,
            entry=65000.0,
            stop_loss=64500.0,
            pip_value_per_standard_lot=0.0,
            tick_size=0.01,
            tick_value=0.01,
            volume_step=0.01,
            volume_min=0.01,
            volume_max=100.0,
        )
        self.assertEqual(quantity, 0.2)

    def test_crypto_quantity_fallback_uses_price_difference(self):
        quantity = calc_quantity(
            "BTCUSD",
            risk_amount=100.0,
            entry=65000.0,
            stop_loss=64500.0,
            account_currency="USD",
            contract_size=1.0,
            volume_step=0.01,
            volume_min=0.01,
            volume_max=100.0,
        )
        self.assertEqual(quantity, 0.2)


if __name__ == "__main__":
    unittest.main()
