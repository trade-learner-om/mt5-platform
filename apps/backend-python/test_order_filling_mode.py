import types
import unittest
from unittest.mock import patch


class OrderFillingModeTests(unittest.TestCase):
    def _info(self, filling_mode: int):
        return types.SimpleNamespace(filling_mode=filling_mode)

    def test_prefers_fok_when_available(self):
        from app.services.metaapi_client import _order_filling_mode

        with patch("app.services.metaapi_client.mt5") as mt5:
            mt5.ORDER_FILLING_FOK = 0
            mt5.ORDER_FILLING_IOC = 1
            mt5.ORDER_FILLING_RETURN = 2
            mt5.SYMBOL_FILLING_FOK = 1
            mt5.SYMBOL_FILLING_IOC = 2
            mt5.SYMBOL_FILLING_RETURN = 4
            self.assertEqual(_order_filling_mode(self._info(1 | 2 | 4)), 0)

    def test_uses_ioc_when_fok_unavailable(self):
        from app.services.metaapi_client import _order_filling_mode

        with patch("app.services.metaapi_client.mt5") as mt5:
            mt5.ORDER_FILLING_FOK = 0
            mt5.ORDER_FILLING_IOC = 1
            mt5.ORDER_FILLING_RETURN = 2
            mt5.SYMBOL_FILLING_FOK = 1
            mt5.SYMBOL_FILLING_IOC = 2
            mt5.SYMBOL_FILLING_RETURN = 4
            self.assertEqual(_order_filling_mode(self._info(2)), 1)

    def test_uses_return_when_only_return_supported(self):
        from app.services.metaapi_client import _order_filling_mode

        with patch("app.services.metaapi_client.mt5") as mt5:
            mt5.ORDER_FILLING_FOK = 0
            mt5.ORDER_FILLING_IOC = 1
            mt5.ORDER_FILLING_RETURN = 2
            mt5.SYMBOL_FILLING_FOK = 1
            mt5.SYMBOL_FILLING_IOC = 2
            mt5.SYMBOL_FILLING_RETURN = 4
            self.assertEqual(_order_filling_mode(self._info(4)), 2)

    def test_empty_bitmask_falls_back_to_ioc(self):
        from app.services.metaapi_client import _order_filling_mode

        with patch("app.services.metaapi_client.mt5") as mt5:
            mt5.ORDER_FILLING_FOK = 0
            mt5.ORDER_FILLING_IOC = 1
            mt5.ORDER_FILLING_RETURN = 2
            mt5.SYMBOL_FILLING_FOK = 1
            mt5.SYMBOL_FILLING_IOC = 2
            mt5.SYMBOL_FILLING_RETURN = 4
            self.assertEqual(_order_filling_mode(self._info(0)), 1)

    def test_filling_mode_diag_includes_chosen_and_bitmask(self):
        from app.services.metaapi_client import _filling_mode_diag

        text = _filling_mode_diag(self._info(6), chosen=1)
        self.assertIn("type_filling=1", text)
        self.assertIn("symbol_filling_mode=6", text)


if __name__ == "__main__":
    unittest.main()
