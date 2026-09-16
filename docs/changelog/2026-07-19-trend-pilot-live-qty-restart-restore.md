# Trend Pilot live quantity and restart restore

## Summary

- Live Trend Pilot active-run cards now show configured lot size on web, iOS, and Android.
- Backend restores `RUNNING` Trend Pilot runs from `trend_pilot_runs` after server restart, rehydrates roll stats, syncs broker positions/orders, and re-subscribes market streams for affected users.

## Backend

- `TrendPilotManager.restore_running_runs` rebuilds in-memory FSMs from persisted run docs.
- Startup restore runs before market-stream restore so active symbols are included in tick routing.
- Failed restores mark the run `STOPPED` and emit `TREND_PILOT_RESTORE_FAILED`.
- `/trend-pilot/active` merges in-memory runs with persisted `RUNNING` rows; `/trend-pilot/runs` returns stopped history only.
- Web live view uses Active/History tabs, hides the start form while a run is active, and shows Stop on each active run card.

## Clients

- Web/iOS/Android active run panels display `quantity` from `/trend-pilot/active`.
- Run history list items include persisted `quantity`.
