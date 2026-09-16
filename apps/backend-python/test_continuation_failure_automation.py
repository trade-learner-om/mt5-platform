import sys
import types
import unittest
from datetime import datetime, timezone


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

from app.services.candle_patterns import (
    continuation_failure_setup_passes_filter,
    is_continuation_failure_setup,
)
from app.services.continuation_failure_automation import (
    CF_EVENT_COLLECTION,
    CF_RUN_COLLECTION,
    ContinuationFailureAutomationManager,
    MAX_CLEAN_STOPLOSSES,
    PENDING_CANDLE_TIMEOUT,
    _infer_direction,
    allocate_target_quantities,
)


def candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def hammer():
    return candle(1.1000, 1.1005, 1.0990, 1.1002)


def shooting_star():
    return candle(1.1005, 1.1015, 1.1000, 1.1003)


class FakeCollection:
    def __init__(self):
        self.records = []

    def update_one(self, query, update, **_kwargs):
        target = next(
            (record for record in self.records if record.get("_id") == query.get("_id")),
            None,
        )
        if target is None:
            for record in self.records:
                if all(record.get(key) == value for key, value in query.items()):
                    target = record
                    break
        if target is not None:
            for key, value in (update.get("$set") or {}).items():
                target[key] = value
            for key in (update.get("$unset") or {}):
                target.pop(key, None)
        return type("Result", (), {"modified_count": 1})()

    def insert_one(self, document):
        self.records.append(document)
        return type("Result", (), {"inserted_id": document.get("_id") or ObjectId()})()

    def find_one(self, query):
        return next(
            (record for record in self.records if all(record.get(key) == value for key, value in query.items())),
            None,
        )

    def find(self, query):
        results = []
        for record in self.records:
            matched = True
            for key, value in query.items():
                if key == "status" and isinstance(value, dict) and "$in" in value:
                    if record.get(key) not in value["$in"]:
                        matched = False
                        break
                elif record.get(key) != value:
                    matched = False
                    break
            if matched:
                results.append(record)
        return results

    def count_documents(self, query):
        return len(self.find(query))

    async def find_async(self, query):
        return self.find(query)

    async def update_one_async(self, query, update, **_kwargs):
        self.update_one(query, update, **_kwargs)


class FakeDb:
    def __init__(self):
        self.runs = FakeCollection()
        self.events = FakeCollection()
        self.orders = FakeCollection()
        self.meta_accounts = FakeCollection()
        self.configs = FakeCollection()

    def __getitem__(self, name):
        if name == CF_RUN_COLLECTION:
            return self.runs
        if name == CF_EVENT_COLLECTION:
            return self.events
        if name == "continuation_failure_configs":
            return self.configs
        raise KeyError(name)


class TimeoutHarness(ContinuationFailureAutomationManager):
    def __init__(self):
        self.cancelled = False
        self.pivot_resets = 0

    def _active_orders(self, _db, _run):
        return [{"status": "PENDING", "cf_is_retry": False}]

    def _has_open_strategy_position(self, _db, _run):
        return False

    async def _cancel_pending_orders(self, db, run, reason, event_type):
        self.cancelled = True

    async def _pivot_reset(self, db, run):
        self.pivot_resets += 1
        direction = str(run.get("direction") or "").upper()
        new_pivot = run.get("hap") if direction == "SHORT" else run.get("lap")
        run["pivot_price"] = float(new_pivot)
        run["status"] = "WAITING_PIVOT_BREACH"


class RetryHarness(ContinuationFailureAutomationManager):
    def __init__(self):
        self.retries = 0
        self.stopped = False
        self.continued = False

    def _active_orders(self, _db, _run):
        return []

    def _has_open_strategy_position(self, _db, _run):
        return False

    async def _place_setup_orders(self, db, run, direction, candle, price, retry=False):
        if retry:
            self.retries += 1

    async def _stop_run_after_stop_limit(self, db, run):
        self.stopped = True
        run["status"] = "STOPPED"

    async def _continue_after_post_target_stop(self, db, run):
        self.continued = True
        run["status"] = "WAITING_PIVOT_BREACH"


class ContinuationFailureAutomationTests(unittest.TestCase):
    def test_direction_inference(self):
        self.assertEqual(_infer_direction(1.1010, 1.1000), "SHORT")
        self.assertEqual(_infer_direction(1.0990, 1.1000), "LONG")
        with self.assertRaises(HTTPException):
            _infer_direction(1.1000, 1.1000)

    def test_short_hammer_and_long_shooting_star_detectors(self):
        self.assertTrue(is_continuation_failure_setup(hammer(), "SHORT"))
        self.assertFalse(is_continuation_failure_setup(hammer(), "LONG"))
        self.assertTrue(is_continuation_failure_setup(shooting_star(), "LONG"))
        self.assertFalse(is_continuation_failure_setup(shooting_star(), "SHORT"))

    def test_short_hammer_filter(self):
        prior = [
            candle(1.1000, 1.1004, 1.0995, 1.1001),
            candle(1.1001, 1.1005, 1.0996, 1.1002),
            candle(1.1002, 1.1006, 1.0997, 1.1003),
        ]
        setup = candle(1.1002, 1.1004, 1.0998, 1.1003)
        self.assertTrue(continuation_failure_setup_passes_filter(setup, prior, "SHORT"))
        rejected = candle(1.1002, 1.1004, 1.0990, 1.1003)
        self.assertFalse(continuation_failure_setup_passes_filter(rejected, prior, "SHORT"))

    def test_long_shooting_star_filter(self):
        prior = [
            candle(1.1010, 1.1015, 1.1005, 1.1012),
            candle(1.1011, 1.1016, 1.1006, 1.1013),
            candle(1.1012, 1.1017, 1.1007, 1.1014),
        ]
        setup = candle(1.1013, 1.1015, 1.1010, 1.1011)
        self.assertTrue(continuation_failure_setup_passes_filter(setup, prior, "LONG"))
        rejected = candle(1.1013, 1.1018, 1.1010, 1.1011)
        self.assertFalse(continuation_failure_setup_passes_filter(rejected, prior, "LONG"))

    def test_allocate_target_quantities(self):
        self.assertEqual(allocate_target_quantities(1.0, [{"price": 1.1}], 0.01), [1.0])
        self.assertEqual(
            allocate_target_quantities(1.0, [{"price": 1.1}, {"price": 1.2}], 0.01),
            [0.5, 0.5],
        )
        self.assertEqual(
            allocate_target_quantities(
                1.0,
                [{"price": 1.1, "quantity": 0.4}, {"price": 1.2}],
                0.01,
            ),
            [0.4, 0.6],
        )
        collapsed = allocate_target_quantities(
            0.01,
            [{"price": 1.1}, {"price": 1.2}, {"price": 1.3}],
            0.01,
        )
        self.assertEqual(collapsed[0], 0.01)
        self.assertEqual(collapsed[1], 0.0)

    def test_pending_timeout_resets_pivot_to_hap(self):
        harness = TimeoutHarness()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "SHORT",
            "hap": 1.1015,
            "lap": None,
            "pending_candles_seen": PENDING_CANDLE_TIMEOUT - 1,
            "placement_candle_time": datetime(2026, 6, 9, 10, 0),
            "status": "ORDER_PENDING",
        }
        db.runs.records.append(run)
        closed = {
            "time": datetime(2026, 6, 9, 10, 6),
            "open": 1.1010,
            "high": 1.1016,
            "low": 1.1008,
            "close": 1.1012,
        }
        import asyncio

        asyncio.run(harness._handle_pending_timeout(db, run, closed, harness._active_orders(db, run)))
        self.assertTrue(harness.cancelled)
        self.assertEqual(harness.pivot_resets, 1)
        self.assertEqual(run["pivot_price"], 1.1015)
        self.assertEqual(run["status"], "WAITING_PIVOT_BREACH")

    def test_clean_stop_triggers_retry(self):
        harness = RetryHarness()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "SHORT",
            "status": "ORDER_OPEN",
            "pending_setup": {"entry": 1.0998, "stop_loss": 1.1006},
        }
        order = {
            "_id": ObjectId(),
            "continuation_failure_run_id": run["_id"],
            "status": "CLOSED",
            "cf_is_retry": False,
            "cf_be_moved": False,
            "cf_partial_6r": False,
            "cf_partial_15r": False,
            "cf_target_booked": False,
            "cf_setup_candle": hammer(),
        }
        db.orders.records.append(order)
        import asyncio

        asyncio.run(harness._refresh_order_outcomes(db, run))
        self.assertEqual(harness.retries, 1)

    def test_second_clean_stop_stops_strategy(self):
        harness = RetryHarness()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "SHORT",
            "status": "ORDER_OPEN",
            "clean_stop_count": 1,
            "pending_setup": {"entry": 1.0998, "stop_loss": 1.1006},
        }
        order = {
            "_id": ObjectId(),
            "continuation_failure_run_id": run["_id"],
            "status": "CLOSED",
            "cf_is_retry": True,
            "cf_be_moved": False,
            "cf_partial_6r": False,
            "cf_partial_15r": False,
            "cf_target_booked": False,
            "cf_setup_candle": hammer(),
        }
        db.orders.records.append(order)
        import asyncio

        asyncio.run(harness._refresh_order_outcomes(db, run))
        self.assertTrue(harness.stopped)
        self.assertEqual(run["status"], "STOPPED")

    def test_post_target_stop_continues(self):
        harness = RetryHarness()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "LONG",
            "status": "ORDER_OPEN",
            "first_target_hit": True,
            "hap": None,
            "lap": 1.0990,
            "pivot_breached": True,
            "clean_stop_count": 1,
        }
        order = {
            "_id": ObjectId(),
            "continuation_failure_run_id": run["_id"],
            "status": "CLOSED",
            "cf_be_moved": True,
            "cf_target_booked": True,
        }
        db.orders.records.append(order)
        import asyncio

        asyncio.run(harness._refresh_order_outcomes(db, run))
        self.assertTrue(harness.continued)
        self.assertEqual(run["status"], "WAITING_PIVOT_BREACH")

    def test_hap_tracks_tick_high_after_breach(self):
        harness = ContinuationFailureAutomationManager()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "SHORT",
            "pivot_breached": True,
            "hap": 1.1010,
        }
        db.runs.records.append(run)
        import asyncio

        asyncio.run(harness._update_extremes_since_breach(db, run, 1.1018))
        self.assertEqual(run["hap"], 1.1018)

    def test_lap_tracks_tick_low_after_breach(self):
        harness = ContinuationFailureAutomationManager()
        db = FakeDb()
        run = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "direction": "LONG",
            "pivot_breached": True,
            "lap": 1.1005,
        }
        db.runs.records.append(run)
        import asyncio

        asyncio.run(harness._update_extremes_since_breach(db, run, 1.0998))
        self.assertEqual(run["lap"], 1.0998)


if __name__ == "__main__":
    unittest.main()
