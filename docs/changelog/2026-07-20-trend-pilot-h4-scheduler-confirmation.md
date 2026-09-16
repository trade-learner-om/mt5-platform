# Trend Pilot H4 scheduler confirmation layer

## Summary

H4 window roll and in-position SL trail now fire from **two paths**:

1. **Tick path (unchanged)** — `on_tick` calls `_on_h4_close` when `last_tick_at >= running_h4_close_at`.
2. **Scheduler path (new)** — per-run `asyncio` task fires at `running_h4_close_at + 15s` so rolls still happen when ticks pause or the websocket is stale.

Both paths call the same `_on_h4_close` logic. A per-run in-progress flag and the existing `c2_time` advance guard prevent double rolls.

## In-position SL hardening

- `apply_window` now syncs `position_id` from the broker via `_find_position` before trailing SL (fixes skipped rolls when `position_id` was stale/null).
- After H4 roll, reversal stop price is verified and replaced if the broker order does not match the computed SL.

## Files

- `apps/backend-python/app/services/trend_pilot_runtime.py` — scheduler, dedup, position sync
- `apps/backend-python/app/main.py` — `set_db_accessor` for background H4 tasks
- `apps/backend-python/test_trend_pilot_h4_scheduler.py` — scheduler and SL roll tests
- `docs/skills/automation.md` — live H4 roll documentation
