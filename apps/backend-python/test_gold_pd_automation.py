import unittest
import sys
import types
from datetime import datetime
from datetime import timezone


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


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.HTTPException = HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

metaapi_client_stub = types.ModuleType("app.services.metaapi_client")
metaapi_client_stub.metaapi_service = object()
sys.modules.setdefault("app.services.metaapi_client", metaapi_client_stub)

m1_candle_builder_stub = types.ModuleType("app.services.m1_candle_builder")
m1_candle_builder_stub._current_price = lambda tick: tick.get("price")
sys.modules.setdefault("app.services.m1_candle_builder", m1_candle_builder_stub)

zoneinfo_stub = types.ModuleType("zoneinfo")
zoneinfo_stub.ZoneInfo = lambda _name: timezone.utc
sys.modules.setdefault("zoneinfo", zoneinfo_stub)

from app.services.gold_pd_automation import (
    GOLD_EVENT_COLLECTION,
    GOLD_RUN_COLLECTION,
    GoldPDAutomationManager,
)


class FakeCollection:
    def __init__(self):
        self.records = []

    def update_one(self, query, update, **_kwargs):
        target = next((record for record in self.records if record.get("_id") == query.get("_id")), None)
        if target is not None:
            for key, value in (update.get("$set") or {}).items():
                target[key] = value
            for key in (update.get("$unset") or {}):
                target.pop(key, None)
        return type("Result", (), {"modified_count": 1})()

    async def update_one_async(self, query, update, **_kwargs):
        return self.update_one(query, update)

    def insert_one(self, document):
        self.records.append(document)
        return type("Result", (), {"inserted_id": document.get("_id") or ObjectId()})()

    def find_one(self, query):
        return next((record for record in self.records if all(record.get(key) == value for key, value in query.items())), None)

    async def find_one_async(self, query):
        return self.find_one(query)


class FakeDb:
    def __init__(self):
        self.runs = FakeCollection()
        self.events = FakeCollection()
        self.orders = FakeCollection()
        self.meta_accounts = FakeCollection()

    def __getitem__(self, name):
        if name == GOLD_RUN_COLLECTION:
            return self.runs
        if name == GOLD_EVENT_COLLECTION:
            return self.events
        raise KeyError(name)


class RetryHarness(GoldPDAutomationManager):
    def __init__(self):
        self.active_orders = []
        self.placements = []

    def _active_orders(self, _db, _run):
        return self.active_orders

    def _has_open_strategy_position(self, _db, _run):
        return False

    async def _place_setup_orders(self, db, run, direction, candle, _price):
        self.placements.append((direction, candle))
        side = "SELL" if direction == "SHORT" else "BUY"
        order = {
            "_id": ObjectId(),
            "account_id": ObjectId(),
            "user_id": run["user_id"],
            "side": side,
            "status": "PENDING",
            "gold_strategy_setup_candle": candle,
            "gold_strategy_setup_high": float(candle["high"]),
            "gold_strategy_setup_low": float(candle["low"]),
            "gold_strategy_next_candle_checked": False,
        }
        self.active_orders.append(order)
        db.orders.records.append(order)
        run["status"] = "ORDER_OPEN"


def candle(minute, open_, high, low, close):
    return {
        "time": datetime(2026, 6, 9, 10, minute),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def base_run(direction):
    return {
        "_id": ObjectId(),
        "user_id": ObjectId(),
        "symbol": "XAUUSD",
        "status": "ARMED",
        "pd_high": 4320,
        "pd_low": 4310,
        "short_armed": direction == "SHORT",
        "long_armed": direction == "LONG",
        "short_blocked": False,
        "long_blocked": False,
    }


class GoldPDAutomationRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_pending_order_cancelled_then_next_green_retries(self):
        manager = RetryHarness()
        db = FakeDb()
        run = base_run("LONG")

        await manager._process_closed_candle(db, run, candle(1, 4308, 4309, 4307, 4308.5), 4308.5)
        self.assertEqual([direction for direction, _ in manager.placements], ["LONG"])

        await manager._process_closed_candle(db, run, candle(2, 4308.5, 4309, 4305, 4306.5), 4306.5)
        self.assertEqual(manager.active_orders[0]["status"], "CANCELLED")

        await manager._process_closed_candle(db, run, candle(3, 4306.5, 4307, 4304, 4306.75), 4306.75)
        self.assertEqual([direction for direction, _ in manager.placements], ["LONG", "LONG"])

    async def test_short_pending_order_cancelled_then_next_red_retries(self):
        manager = RetryHarness()
        db = FakeDb()
        run = base_run("SHORT")

        await manager._process_closed_candle(db, run, candle(1, 4322, 4323, 4321, 4321.5), 4321.5)
        self.assertEqual([direction for direction, _ in manager.placements], ["SHORT"])

        await manager._process_closed_candle(db, run, candle(2, 4321.5, 4324, 4321, 4323.5), 4323.5)
        self.assertEqual(manager.active_orders[0]["status"], "CANCELLED")

        await manager._process_closed_candle(db, run, candle(3, 4323.5, 4325, 4322, 4322.5), 4322.5)
        self.assertEqual([direction for direction, _ in manager.placements], ["SHORT", "SHORT"])


if __name__ == "__main__":
    unittest.main()
