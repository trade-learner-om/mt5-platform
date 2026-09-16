# Trend Pilot H4 completed-candle detection fix

## Summary

Fixed stale C1/C2 after an H4 close when the candle feed did not include a forming bar. The runtime always used `candles[:-1]`, which dropped the newest **completed** bar when MT5 returned only closed candles. That blocked window rolls (e.g. Jul 20 4:00 AM close not advancing C2 past Jul 20 12:00 AM).

## Changes

- `completed_h4_candles()` — drop the last bar only when its close time is still in the future
- H4 roll fetches now force a fresh MT5 pull (`for_roll=True`)
- `GET /trend-pilot/active` triggers an overdue H4 roll catch-up when past `running_h4_close_at + 15s`

## Changes (follow-up)

- `latest_contiguous_h4_pair()` — ignore gapped suffixes (e.g. Jul 17 + Jul 20) and use the last two consecutive H4 bars
- H4 roll fetch uses `get_backtest_h4_candles` range pull for contiguous broker history
- `ensure_user_runs_in_memory()` on `/trend-pilot/active` restores RUNNING rows not in the live manager
- Overdue catch-up loops up to 8 roll passes per active poll
