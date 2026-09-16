# Trend Pilot $10 entry/SL buffer

## Changed

- Added `apps/backend-python/app/services/trend_pilot_levels.py` with a fixed `TREND_PILOT_PRICE_BUFFER_USD = 10.0`.
- Live runtime and backtest now apply buffered entry and stop-loss levels on every arm, entry, and reversal.
- Roll/event payloads include `price_buffer_usd`, `buffered_entry`, and `buffered_stop_loss`.
- Trend Pilot dashboard Active Run panel shows buffered long/short entry and SL levels.

## Tests

- `apps/backend-python/test_trend_pilot_levels.py`
- Updated `apps/backend-python/test_trend_pilot_backtest.py`
