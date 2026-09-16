# MongoDB

## Purpose

Persist users, encrypted MT5 credentials, and operational logs.

## Implementation

MongoDB integration lives in `apps/backend-python/app/db.py` and uses `motor.motor_asyncio.AsyncIOMotorClient`.

The backend currently exposes MongoDB through a Motor-backed compatibility layer:

- async entrypoints can call native async helpers such as `find_one_async()` and `command_async()`;
- legacy collection-style code can keep using `find_one()`, `find()`, `update_one()`, `bulk_write()`, and similar methods while the compatibility layer submits those Motor operations onto the dedicated Motor event loop.

This keeps the repository compatible during the migration away from older synchronous call sites while ensuring MongoDB traffic is served by Motor instead of the previous direct `pymongo.MongoClient`.

## Collections

- `users`: unique `username`, bcrypt `password_hash`, session state, admin flags, selected account ids, timestamps.
- `meta_accounts`: encrypted MT5 credentials, broker metadata, selected risk and symbol alias settings.
- `orders`, `order_events`, `notifications`, `trade_plans`, strategy collections, candle caches, and market-specific watchlists.

## Dependencies

- Local MongoDB at `mongodb://localhost:27017`
- Python `motor`
- `pymongo` operation helpers for indexes and bulk-write models
- Database name `mt5_platform`

## Usage Example

Use the shared database proxy from `app.db` instead of creating ad hoc clients:

- `db.users.find_one(...)`
- `await db.users.find_one_async(...)`
- `db.orders.find({...}).sort("updated_at", -1)`
- `await db.command_async("ping")`
