# Websocket Live State

## Purpose

Preserve the reference app's websocket-first state model.

## Implementation

The backend exposes `WS /ws/live` from `apps/backend-python/app/main.py`. Live snapshots are built by `apps/backend-python/app/services/state_manager.py` and include:

- international prices and watchlist
- Indian market overview and watchlist
- active/recent orders
- notifications
- scheduled trades (`scheduled_trades`)

The frontend opens the socket from `apps/frontend-react/src/api.js` and treats websocket payloads as the primary source for live state. REST endpoints should be used for explicit commands and initial hydration, not repeated UI polling.

`/ws/live` sends an application heartbeat every 20 seconds and responds to client `ping` messages with `pong`. Web, Android, and iOS clients also send periodic `ping` traffic so idle browser tabs and mobile background sessions do not get dropped by proxies before alert snapshots arrive.

The React frontend no longer renders a price chart. `/ws/live` is now used for the chartless execution terminal: watchlist tick animation, trap-reversal distance tracking, order-ticket live pricing, and active-order distance-to-target/SL displays.

## Local MT5 Notes

The local MT5 stream polls subscribed symbols once per second through `apps/backend-python/app/services/metaapi_client.py`. An MT5 Expert Advisor or bridge may also push ticks into `WS /ws/mt5/ticks`, but live state does not require an EA when backend polling is available.

`WS /ws/mt5/ticks` requires the per-account tick ingest secret shown in Manage Accounts and accepts either one tick:

```json
{ "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002, "time": "2026-06-18T03:30:00Z" }
```

or a batch:

```json
{ "account_id": "12345678", "ticks": [{ "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002 }] }
```

Accepted ticks flow through `market_data_stream.handle_price()`, so the trap-reversal FSM, M1 candle builder, planner runtime, and `/ws/live` snapshots continue to use one backend event path.
