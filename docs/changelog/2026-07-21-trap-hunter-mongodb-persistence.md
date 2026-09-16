# Trap Hunter MongoDB persistence and Live history

## Summary

Trap Hunter live runs are now persisted in MongoDB (`trap_hunter_runs`) instead of living only in memory. Runs survive backend restarts and are restored on startup. The Live tab now has **Active** and **History** sub-tabs, matching Trend Pilot.

## Backend

- Added `trap_hunter_run_persistence.py` for run documents, engine-state serialize/restore, and history serializers.
- `trap_hunter_runtime.py` creates/updates/stops run docs on start, tick, and stop; restores running runs on startup and lazy-restore on tick.
- New API routes:
  - `GET /trap-hunter/runs?limit=20` — stopped run list
  - `GET /trap-hunter/history/{run_id}` — run detail with trades and session rolls
- `GET /trap-hunter/active` is DB-backed via `snapshot_for_user`.
- MongoDB indexes for `trap_hunter_runs` and `trap_hunter_trades.run_id`.
- Market data stream subscribes to symbols from DB-backed active Trap Hunter runs.

## Frontend

- Trap Hunter Live view: **Active** / **History** tabs.
- History rows reuse `TrapHunterBacktestRow` in `mode="live"` with run detail from `/trap-hunter/history/{run_id}`.

## Notes

- In-memory `active_runs` remains a runtime cache for tick processing; MongoDB is the source of truth (same pattern as Trend Pilot).
