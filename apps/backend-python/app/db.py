import asyncio
import atexit
import inspect
import threading
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from .config import settings


class CursorProxy:
    def __init__(self, runtime: "MotorRuntime", cursor):
        self._runtime = runtime
        self._cursor = cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def __iter__(self):
        return iter(self._runtime.run(self._cursor.to_list, length=None))

    async def to_list(self, length: Optional[int] = None):
        return await self._runtime.run_async(self._cursor.to_list, length=length)


class CollectionProxy:
    def __init__(self, runtime: "MotorRuntime", collection):
        self._runtime = runtime
        self._collection = collection

    def find_one(self, *args, **kwargs):
        return self._runtime.run(self._collection.find_one, *args, **kwargs)

    async def find_one_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.find_one, *args, **kwargs)

    def find(self, *args, **kwargs):
        return CursorProxy(self._runtime, self._collection.find(*args, **kwargs))

    async def find_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.find(*args, **kwargs).to_list, length=None)

    def aggregate(self, *args, **kwargs):
        return CursorProxy(self._runtime, self._collection.aggregate(*args, **kwargs))

    def insert_one(self, *args, **kwargs):
        return self._runtime.run(self._collection.insert_one, *args, **kwargs)

    async def insert_one_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.insert_one, *args, **kwargs)

    def insert_many(self, *args, **kwargs):
        return self._runtime.run(self._collection.insert_many, *args, **kwargs)

    async def insert_many_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.insert_many, *args, **kwargs)

    def update_one(self, *args, **kwargs):
        return self._runtime.run(self._collection.update_one, *args, **kwargs)

    async def update_one_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.update_one, *args, **kwargs)

    def update_many(self, *args, **kwargs):
        return self._runtime.run(self._collection.update_many, *args, **kwargs)

    async def update_many_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.update_many, *args, **kwargs)

    def find_one_and_update(self, *args, **kwargs):
        return self._runtime.run(self._collection.find_one_and_update, *args, **kwargs)

    async def find_one_and_update_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.find_one_and_update, *args, **kwargs)

    def delete_one(self, *args, **kwargs):
        return self._runtime.run(self._collection.delete_one, *args, **kwargs)

    async def delete_one_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.delete_one, *args, **kwargs)

    def delete_many(self, *args, **kwargs):
        return self._runtime.run(self._collection.delete_many, *args, **kwargs)

    async def delete_many_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.delete_many, *args, **kwargs)

    def count_documents(self, *args, **kwargs):
        return self._runtime.run(self._collection.count_documents, *args, **kwargs)

    async def count_documents_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.count_documents, *args, **kwargs)

    def distinct(self, *args, **kwargs):
        return self._runtime.run(self._collection.distinct, *args, **kwargs)

    async def distinct_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.distinct, *args, **kwargs)

    def bulk_write(self, *args, **kwargs):
        return self._runtime.run(self._collection.bulk_write, *args, **kwargs)

    async def bulk_write_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._collection.bulk_write, *args, **kwargs)

    def create_index(self, *args, **kwargs):
        return self._runtime.run(self._collection.create_index, *args, **kwargs)

    def drop_index(self, *args, **kwargs):
        return self._runtime.run(self._collection.drop_index, *args, **kwargs)

    async def aggregate_async(self, pipeline, **kwargs):
        return await self._runtime.run_async(self._collection.aggregate(pipeline, **kwargs).to_list, length=None)


class DatabaseProxy:
    def __init__(self, runtime: "MotorRuntime", database):
        self._runtime = runtime
        self._database = database

    def __getattr__(self, name: str):
        return CollectionProxy(self._runtime, getattr(self._database, name))

    def __getitem__(self, name: str):
        return CollectionProxy(self._runtime, self._database[name])

    def command(self, *args, **kwargs):
        return self._runtime.run(self._database.command, *args, **kwargs)

    async def command_async(self, *args, **kwargs):
        return await self._runtime.run_async(self._database.command, *args, **kwargs)


class MotorRuntime:
    def __init__(self, mongodb_url: str, db_name: str):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="motor-runtime", daemon=True)
        self._thread.start()
        self._client = AsyncIOMotorClient(
            mongodb_url,
            io_loop=self._loop,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        self.database = DatabaseProxy(self, self._client[db_name])
        atexit.register(self.close)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro_fn, /, *args, **kwargs):
        result = coro_fn(*args, **kwargs)
        if not inspect.isawaitable(result):
            return result

        async def _await_result(awaitable):
            return await awaitable

        future = asyncio.run_coroutine_threadsafe(_await_result(result), self._loop)
        return future.result()

    async def run_async(self, coro_fn, /, *args, **kwargs):
        result = coro_fn(*args, **kwargs)
        if not inspect.isawaitable(result):
            return result

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is self._loop:
            return await result

        async def _await_result(awaitable):
            return await awaitable

        future = asyncio.run_coroutine_threadsafe(_await_result(result), self._loop)
        return await asyncio.wrap_future(future)

    def close(self):
        if getattr(self, "_client", None) is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if getattr(self, "_loop", None) is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


motor_runtime = MotorRuntime(settings.mongodb_url, settings.mongodb_db_name)
database = motor_runtime.database

database.users.create_index([("username", ASCENDING)], unique=True)
database.meta_accounts.create_index([("user_id", ASCENDING)])
database.watchlist_items.create_index([("user_id", ASCENDING), ("symbol", ASCENDING)], unique=True)
database.indian_watchlist_items.create_index([("user_id", ASCENDING), ("account_id", ASCENDING), ("symbol", ASCENDING)], unique=True)
database.indian_broker_sessions.create_index([("user_id", ASCENDING), ("account_id", ASCENDING)], unique=True)
database.orders.create_index([("user_id", ASCENDING), ("updated_at", ASCENDING)])
database.orders.create_index([("meta_order_id", ASCENDING)], unique=False)
database.orders.create_index(
    [
        ("user_id", ASCENDING),
        ("account_id", ASCENDING),
        ("status", ASCENDING),
        ("manual_context.automatic_trade_management", ASCENDING),
    ]
)
database.orders.create_index(
    [
        ("user_id", ASCENDING),
        ("account_id", ASCENDING),
        ("status", ASCENDING),
        ("manual_context.retryable_order", ASCENDING),
        ("manual_context.retry_used", ASCENDING),
    ]
)
database.order_events.create_index([("order_id", ASCENDING), ("event_ts_ist", ASCENDING)])
database.order_events.create_index([("run_id", ASCENDING), ("strategy_type", ASCENDING), ("event_ts_ist", ASCENDING)])
database.strategy_results.create_index([("user_id", ASCENDING), ("strategy_type", ASCENDING), ("created_at", DESCENDING)])
database.master_break_runs.create_index([("user_id", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)])
database.notifications.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])
database.notifications.create_index([("user_id", ASCENDING), ("category", ASCENDING), ("created_at", ASCENDING)])
database.notifications.create_index([("user_id", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)])
database.h1_candles.create_index(
    [("broker_key", ASCENDING), ("symbol", ASCENDING), ("timeframe", ASCENDING), ("timestamp", ASCENDING)],
    unique=True,
)
database.h1_candles.create_index([("broker_key", ASCENDING), ("symbol", ASCENDING), ("timestamp", ASCENDING)])
database.analysis_candles.create_index(
    [("broker_key", ASCENDING), ("symbol", ASCENDING), ("timeframe", ASCENDING), ("timestamp", ASCENDING)],
    unique=True,
)
database.analysis_candles.create_index([("broker_key", ASCENDING), ("symbol", ASCENDING), ("timeframe", ASCENDING)])
database.candles.create_index(
    [
        ("broker", ASCENDING),
        ("broker_account_id", ASCENDING),
        ("market", ASCENDING),
        ("symbol", ASCENDING),
        ("timeframe", ASCENDING),
        ("time", ASCENDING),
    ],
    unique=True,
)
database.candles.create_index(
    [
        ("broker", ASCENDING),
        ("broker_account_id", ASCENDING),
        ("symbol", ASCENDING),
        ("timeframe", ASCENDING),
        ("time", DESCENDING),
    ]
)
database.trade_plans.create_index([("user_id", ASCENDING), ("account_id", ASCENDING), ("symbol", ASCENDING), ("updated_at", ASCENDING)])
database.platform_users.create_index([("username", ASCENDING)], unique=True)
database.platform_users.create_index([("email", ASCENDING)], unique=False, sparse=True)
database.platform_audit_logs.create_index([("ts", DESCENDING)])
database.platform_audit_logs.create_index([("app", ASCENDING), ("category", ASCENDING), ("ts", DESCENDING)])
database.platform_audit_logs.create_index([("user_id", ASCENDING), ("ts", DESCENDING)])


def get_db():
    yield database


def parse_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise ValueError("Invalid ObjectId") from exc


def oid_str(value) -> str:
    return str(value)
