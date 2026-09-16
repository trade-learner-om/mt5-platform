# WebSocket live stream lock event-loop fix

## Problem

`/ws/live` connections failed with `RuntimeError: asyncio.Lock ... is bound to a different event loop` after the per-user stream lock was introduced. Locks were cached per user but first created on temporary loops from `run_coro_in_thread(asyncio.run(...))`, then reused on the uvicorn WebSocket loop.

## Fix

Scope stream ensure locks per running event loop via `WeakKeyDictionary`, so each loop gets its own `asyncio.Lock` and discarded temporary loops do not poison the cache.
