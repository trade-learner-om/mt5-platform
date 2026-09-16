# WebSocket reconnect and MT5 polling restart storm fix

## Summary

- Shared `LocalMT5Connection` instances per MT5 account with ref-counted release so primary and execution streams do not run duplicate poll loops.
- Skip separate execution streams when the primary session already covers required symbols (Trend Pilot on local MT5).
- Debounce `/ws/live` stream refresh and heartbeat-driven `refresh_live_stream` calls.
- Harden live websocket heartbeat so refresh failures no longer tear down the socket.
- Reduce frontend reconnect churn on transient socket errors and relax stale watchdog timing.

## Backend

- `LocalMT5StreamingPool` in `metaapi_client.py`; `connect_streaming_account` acquires, `close()` releases.
- `market_data_stream.refresh_live_stream` debounces full setup for 25s unless stream missing or stale.
- `_ensure_execution_stream` skips when primary symbols are a superset.
- `ws_live.py` refreshes streams at most every 60s from heartbeat; errors are logged, not fatal.

## Frontend

- `App.jsx` ignores `onError` when socket is still OPEN/CONNECTING; stale watchdog uses 1.5x threshold.
