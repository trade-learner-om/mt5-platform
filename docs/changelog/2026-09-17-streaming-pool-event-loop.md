# Streaming pool event-loop lock fix

## Problem

`POST /watchlist`, `/ws/live` heartbeat, and order reconcile failed with `RuntimeError: asyncio.Lock ... is bound to a different event loop` in `LocalMT5StreamingPool.acquire`. The pool lock was created on a throwaway loop from `run_coro_in_thread(asyncio.run(...))`, then reused on the uvicorn websocket/tick loops. That also left live prices (and Scheduled Trade LTP) empty.

## Fix

- Guard streaming-pool dict mutations with a `threading.Lock` and never await while it is held.
- Hop live-stream restore/ensure/refresh/reconcile/tick ingest and websocket subscribe/heartbeat onto `market_data_stream`'s dedicated tick loop instead of a new `asyncio.run` loop.
- Scope scheduled-trade and tick-processing `asyncio.Lock` objects per running loop.
- Subscribe Scheduled Trade form and lifecycle symbols into `/ws/live` extra prices.
