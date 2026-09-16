# MT5 price polling restart storm fix

## Problem

Rapid `/ws/live` reconnects could trigger overlapping `_refresh_user_streams` and `refresh_live_stream` calls. Concurrent stream setup tore down and recreated `LocalMT5Connection` polling loops, spamming `Restarting local MT5 price polling` for the same account.

## Fix

- Per-user `asyncio.Lock` around `ensure_user_stream` and `refresh_live_stream` in `market_data_stream.py`
- Skip duplicate in-flight `_refresh_user_streams` tasks per user in `main.py`
- Log `Starting local MT5 price polling` at INFO on first start; reserve WARNING for true restarts
