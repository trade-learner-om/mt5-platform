# Trend Pilot H4 schedule and reliable stop orders

## Summary

- H4 candles are fetched only when the forming H4 bar closes (`running_h4_close_at`), not on every tick.
- Per-tick work is limited to fill detection, post-H4 extreme tracking, and broker order watchdogs.
- Pre-entry stops use adaptive breach entries (`post_h4_high` / `post_h4_low`) while price stays beyond the C1C2 buffered level; on full pullback (both bid and ask inside the window entry), stops revert to C1C2 prices immediately via watchdog broker-price sync.
- Active runs API exposes `c1c2_*` and `adaptive_*` entry fields; UI shows C1C2 entry/SL always and adaptive entry only when active.
- After first entry, runs stay in position with a 2x reversal stop; restore and recovery paths hardened.
- Order placement/sync events persisted on `trend_pilot_runs.order_status` and `order_events`.

## Frontend

- Active Trend Pilot runs show a live price with the same animated up/down styling as the terminal watchlist.

## Backend

- `TrendPilotFSM._on_h4_close` rolls window on schedule; `handle_price` no longer loads H4 data per tick.
- `arm_stops` validates both entry order ids, rolls back partial placement, and blocks post-entry arming.
- `metaapi_client._order_dict` includes `side` and `order_type` for broker order sync.
- `entry_levels_for_arm`, `run_has_entered`, `persist_order_status` helpers.
