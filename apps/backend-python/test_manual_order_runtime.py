import asyncio
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


class ObjectId:
    _counter = 0

    def __init__(self, value=None):
        if value is None:
            ObjectId._counter += 1
            value = f"fake-object-id-{ObjectId._counter}"
        self.value = str(value)

    def __str__(self):
        return self.value

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.value)


bson_stub = types.ModuleType("bson")
bson_stub.ObjectId = ObjectId
sys.modules.setdefault("bson", bson_stub)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.updates = []

    def _resolve(self, doc, key):
        if isinstance(key, str) and "." in key:
            value = doc
            for part in key.split("."):
                value = (value or {}).get(part)
            return value
        return doc.get(key)

    def _match_expected(self, value, expected):
        if isinstance(expected, dict):
            if "$in" in expected:
                return value in expected["$in"]
            if "$ne" in expected:
                return value != expected["$ne"]
            return False
        return value == expected

    def find(self, query, projection=None):
        def matches(doc, clause=None):
            source = clause if clause is not None else query
            for key, expected in source.items():
                if key == "$or":
                    if not any(matches(doc, item) for item in expected):
                        return False
                    continue
                value = self._resolve(doc, key)
                if not self._match_expected(value, expected):
                    return False
            return True

        return [doc for doc in self.docs if matches(doc)]

    def find_one(self, query):
        results = self.find(query)
        return results[0] if results else None

    async def find_async(self, query, projection=None):
        return self.find(query, projection)

    async def find_one_async(self, query):
        return self.find_one(query)

    def find_one_and_update(self, query, update):
        doc = self.find_one(query)
        if not doc:
            return None
        for key, value in (update.get("$set") or {}).items():
            if "." in key:
                root, child = key.split(".", 1)
                doc.setdefault(root, {})
                doc[root][child] = value
            else:
                doc[key] = value
        self.updates.append((query, update))
        return dict(doc)

    async def find_one_and_update_async(self, query, update):
        return self.find_one_and_update(query, update)

    def update_one(self, query, update):
        doc = self.find_one(query)
        if not doc:
            return MagicMock(matched_count=0)
        for key, value in (update.get("$set") or {}).items():
            if "." in key:
                root, child = key.split(".", 1)
                doc.setdefault(root, {})
                doc[root][child] = value
            else:
                doc[key] = value
        self.updates.append((query, update))
        return MagicMock(matched_count=1)

    async def update_one_async(self, query, update):
        return self.update_one(query, update)

    def insert_one(self, doc):
        new_doc = dict(doc)
        new_doc["_id"] = ObjectId()
        self.docs.append(new_doc)
        result = MagicMock()
        result.inserted_id = new_doc["_id"]
        return result

    async def insert_one_async(self, doc):
        return self.insert_one(doc)


class FakeDB:
    def __init__(self, orders=None, events=None, notifications=None):
        self.orders = FakeCollection(orders)
        self.order_events = FakeCollection(events)
        self.notifications = FakeCollection(notifications)
        self.meta_accounts = FakeCollection([{"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}])


metaapi_client_stub = types.ModuleType("app.services.metaapi_client")


class MetaApiStub:
    close_position = AsyncMock()
    place_pending_order = AsyncMock(return_value={"orderId": "broker-99"})
    now_ist = staticmethod(lambda: "18 Jun 2026, 03:30:00 PM IST")
    serialize_payload = staticmethod(lambda payload: str(payload))


metaapi_client_stub.metaapi_service = MetaApiStub()
sys.modules.setdefault("app.services.metaapi_client", metaapi_client_stub)

from app.services.manual_order_runtime import (  # noqa: E402
    ManualOrderRuntimeManager,
    _is_clean_stop_close,
    _risk_reward,
    _target_reached,
)


class ManualOrderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.manager = ManualOrderRuntimeManager()
        MetaApiStub.close_position.reset_mock()
        MetaApiStub.place_pending_order.reset_mock()

    def test_risk_reward_buy(self):
        order = {"side": "BUY", "entry": 100.0, "stop_loss": 90.0}
        self.assertAlmostEqual(_risk_reward(order, 120.0), 2.0)

    def test_target_reached_buy(self):
        order = {"side": "BUY", "target": 110.0}
        self.assertTrue(_target_reached(order, 110.5))
        self.assertFalse(_target_reached(order, 109.0))

    def test_clean_stop_close_requires_position_and_no_management(self):
        order = {
            "manual_context": {"position_was_open": True, "partial_booked_4r": False, "target_booked": False},
            "realized_pl": -10.0,
            "target": 120.0,
            "entry": 100.0,
            "stop_loss": 90.0,
            "side": "BUY",
        }
        self.assertTrue(_is_clean_stop_close(order))

    def test_clean_stop_close_rejects_target_booked(self):
        order = {
            "manual_context": {"position_was_open": True, "partial_booked_4r": False, "target_booked": True},
            "realized_pl": 20.0,
        }
        self.assertFalse(_is_clean_stop_close(order))

    def test_manage_open_positions_books_half_at_4r(self):
        order = {
            "_id": ObjectId("order-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "EURUSD",
            "side": "BUY",
            "entry": 1.1000,
            "stop_loss": 1.0900,
            "target": 1.1400,
            "quantity": 1.0,
            "position_quantity": 1.0,
            "status": "POSITION_OPEN",
            "meta_position_id": "pos-1",
            "manual_context": {"automatic_trade_management": True, "partial_booked_4r": False, "target_booked": False},
            "broker_info": {},
        }
        db = FakeDB(orders=[order])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}

        asyncio.run(self.manager._manage_open_positions(db, ObjectId("user-1"), account, "EURUSD", 1.1410))

        MetaApiStub.close_position.assert_awaited_once()
        args = MetaApiStub.close_position.await_args.args
        self.assertEqual(args[3], 0.5)
        updated = db.orders.find_one({"_id": order["_id"]})
        self.assertTrue(updated["manual_context"]["partial_booked_4r"])

    def test_retry_places_single_sl_child(self):
        parent = {
            "_id": ObjectId("parent-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "EURUSD",
            "order_type": "LIMIT",
            "side": "BUY",
            "entry": 1.1000,
            "stop_loss": 1.0900,
            "target": 1.1300,
            "quantity": 0.2,
            "risk_amount": 100.0,
            "sl_pips": 10.0,
            "status": "CLOSED",
            "realized_pl": -5.0,
            "manual_context": {
                "retryable_order": True,
                "retry_used": False,
                "position_was_open": True,
                "automatic_trade_management": True,
                "partial_booked_4r": False,
                "target_booked": False,
            },
            "broker_info": {},
            "copy_group_id": "group-1",
        }
        db = FakeDB(orders=[parent])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}

        asyncio.run(self.manager._process_retryable_closes(db, ObjectId("user-1"), account))

        self.assertEqual(len(db.orders.docs), 2)
        parent_updated = db.orders.find_one({"_id": parent["_id"]})
        self.assertTrue(parent_updated["manual_context"]["retry_used"])
        child = [doc for doc in db.orders.docs if doc.get("manual_context", {}).get("is_retry_child")][0]
        self.assertEqual(child["order_type"], "SL")
        self.assertEqual(child["entry"], parent["entry"])
        self.assertFalse(child["manual_context"]["retryable_order"])
        MetaApiStub.place_pending_order.assert_awaited_once()

    def test_retry_places_single_sl_child_for_sl_parent(self):
        parent = {
            "_id": ObjectId("parent-sl-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "EURUSD",
            "order_type": "SL",
            "side": "BUY",
            "entry": 1.1000,
            "stop_loss": 1.0900,
            "target": 1.1300,
            "quantity": 0.2,
            "risk_amount": 100.0,
            "sl_pips": 10.0,
            "status": "CLOSED",
            "realized_pl": -5.0,
            "manual_context": {
                "retryable_order": True,
                "retry_used": False,
                "position_was_open": True,
                "automatic_trade_management": True,
                "partial_booked_4r": False,
                "target_booked": False,
            },
            "broker_info": {},
        }
        db = FakeDB(orders=[parent])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}

        asyncio.run(self.manager._process_retryable_closes(db, ObjectId("user-1"), account))

        self.assertEqual(len(db.orders.docs), 2)
        child = [doc for doc in db.orders.docs if doc.get("manual_context", {}).get("is_retry_child")][0]
        self.assertEqual(child["order_type"], "SL")
        MetaApiStub.place_pending_order.assert_awaited_once()

    def test_retry_child_does_not_retry_again(self):
        child = {
            "_id": ObjectId("child-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "EURUSD",
            "order_type": "SL",
            "side": "BUY",
            "entry": 1.1000,
            "stop_loss": 1.0900,
            "quantity": 0.2,
            "status": "CLOSED",
            "realized_pl": -5.0,
            "manual_context": {
                "retryable_order": False,
                "retry_used": False,
                "is_retry_child": True,
                "position_was_open": True,
                "partial_booked_4r": False,
                "target_booked": False,
            },
            "broker_info": {},
        }
        db = FakeDB(orders=[child])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}

        asyncio.run(self.manager._process_retryable_closes(db, ObjectId("user-1"), account))

        self.assertEqual(len(db.orders.docs), 1)
        MetaApiStub.place_pending_order.assert_not_awaited()

    def test_active_symbols_includes_conditional_waiting(self):
        order = {
            "_id": ObjectId("cond-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "XAUUSD",
            "order_type": "SL",
            "status": "WAITING_TRIGGER",
            "manual_context": {"conditional_order": True, "trigger_price": 2650.0},
        }
        db = FakeDB(orders=[order])
        symbols = self.manager.active_symbols(db, ObjectId("user-1"), ObjectId("account-1"))
        self.assertIn("XAUUSD", symbols)

    def test_conditional_sell_places_sl_when_ask_crosses_trigger(self):
        order = {
            "_id": ObjectId("cond-sell-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "XAUUSD",
            "order_type": "SL",
            "side": "SELL",
            "entry": 2640.0,
            "stop_loss": 2655.0,
            "target": 2620.0,
            "quantity": 0.1,
            "status": "WAITING_TRIGGER",
            "manual_context": {
                "conditional_order": True,
                "conditional_triggered": False,
                "trigger_price": 2650.0,
            },
            "broker_info": {},
        }
        db = FakeDB(orders=[order])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}
        price = {"symbol": "XAUUSD", "bid": 2649.5, "ask": 2650.2, "price": 2649.85}

        asyncio.run(self.manager._process_conditional_triggers(db, ObjectId("user-1"), account, "XAUUSD", price))

        updated = db.orders.find_one({"_id": order["_id"]})
        self.assertEqual(updated["status"], "PENDING")
        self.assertTrue(updated["manual_context"]["conditional_triggered"])
        self.assertEqual(updated["meta_order_id"], "broker-99")
        MetaApiStub.place_pending_order.assert_awaited_once()

    def test_conditional_buy_does_not_place_before_trigger(self):
        order = {
            "_id": ObjectId("cond-buy-1"),
            "user_id": ObjectId("user-1"),
            "account_id": ObjectId("account-1"),
            "symbol": "XAUUSD",
            "order_type": "SL",
            "side": "BUY",
            "entry": 2660.0,
            "stop_loss": 2645.0,
            "quantity": 0.1,
            "status": "WAITING_TRIGGER",
            "manual_context": {
                "conditional_order": True,
                "conditional_triggered": False,
                "trigger_price": 2650.0,
            },
            "broker_info": {},
        }
        db = FakeDB(orders=[order])
        account = {"_id": ObjectId("account-1"), "api_token": "token", "account_id": "123"}
        price = {"symbol": "XAUUSD", "bid": 2651.0, "ask": 2651.5, "price": 2651.25}

        asyncio.run(self.manager._process_conditional_triggers(db, ObjectId("user-1"), account, "XAUUSD", price))

        updated = db.orders.find_one({"_id": order["_id"]})
        self.assertEqual(updated["status"], "WAITING_TRIGGER")
        MetaApiStub.place_pending_order.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
