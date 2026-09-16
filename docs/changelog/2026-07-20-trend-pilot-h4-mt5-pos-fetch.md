# Trend Pilot H4 sync: use native MT5 copy_rates_from_pos

## Summary

Trend Pilot H4 window sync now uses MT5 `copy_rates_from_pos` (native `TIMEFRAME_H4`) and drops the last bar as the forming candle — matching the candle-detector pattern. Removes brittle `copy_rates_range` and UTC-based forming-bar detection for live sync.

## Changes

- `get_fresh_h4_candles()` — `get_historical_candles(..., limit=20)` only
- `completed_h4_candles(..., from_mt5=True)` — `candles[:-1]` MT5 convention
- `fetch_mt5_h4_completed()` — unified fetch + completed helper for sync/roll
- Start, sync, and roll all use the same MT5 path with `from_mt5=True`
- Sync errors show raw vs completed bar counts
