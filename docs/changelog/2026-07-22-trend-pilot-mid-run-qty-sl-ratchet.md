# Trend Pilot mid-run updates and non-widening SL

## Changed

- Live Trend Pilot controls (quantity + accounts) stay available while runs are active.
- New `POST /trend-pilot/update` applies quantity to existing runs and starts newly selected accounts.
- Quantity changes do not resize open positions; opposite pending stop is refreshed so the next flip uses the new size.
- Late-joined accounts set `deferred_entry_side` to the opposite of peers already in position (join on the next trade).
- In-position C1/C2 window rolls never widen SL: Long uses `max(previous, candidate)`, Short uses `min(previous, candidate)` (live + backtest).
- Running trades: `position_stop_loss` is persisted; restore and broker `modify_position` ratchet against broker + stored SL so an open trade is never widened.

## Tests

- `apps/backend-python/test_trend_pilot_levels.py`
- `apps/backend-python/test_trend_pilot_backtest.py`
