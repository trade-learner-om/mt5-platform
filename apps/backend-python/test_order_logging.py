import unittest

from app.services.order_logging import append_order_log_prices, format_order_log_prices, merge_order_log_payload


class OrderLoggingTests(unittest.TestCase):
    def test_format_order_log_prices(self):
        text = format_order_log_prices(
            {
                "side": "BUY",
                "entry": 2650.12,
                "stop_loss": 2645.0,
                "target": 2660.0,
                "quantity": 0.1,
                "bid": 2649.5,
                "ask": 2649.8,
            }
        )
        self.assertIn("BUY", text)
        self.assertIn("entry 2650.12", text)
        self.assertIn("SL 2645", text)
        self.assertIn("TP 2660", text)
        self.assertIn("qty 0.1", text)
        self.assertIn("bid 2649.5", text)
        self.assertIn("ask 2649.8", text)

    def test_append_order_log_prices(self):
        message = append_order_log_prices(
            "MT5 order rejected: retcode=10015 comment=Invalid price",
            entry=2650.0,
            stop_loss=2645.0,
            side="BUY",
            bid=2649.0,
            ask=2650.0,
        )
        self.assertTrue(message.startswith("MT5 order rejected"))
        self.assertIn("entry 2650", message)
        self.assertIn("SL 2645", message)

    def test_merge_order_log_payload(self):
        payload = merge_order_log_payload({"error": "Invalid price"}, source={"entry": 1.1, "stop_loss": 1.0, "side": "buy"})
        self.assertEqual(payload["error"], "Invalid price")
        self.assertEqual(payload["entry"], 1.1)
        self.assertEqual(payload["stop_loss"], 1.0)
        self.assertEqual(payload["side"], "BUY")


if __name__ == "__main__":
    unittest.main()
