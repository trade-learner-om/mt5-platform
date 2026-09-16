# 2026-07-09 - Trap Reversal Pivot

## Removed

- Deleted the legacy Swings, Unmitigated Swings, GOLD Strategy, and Continuation Failure web pages and their header navigation links.
- Removed the old backend route families for:
  - `POST /analysis/market-structure`
  - `POST /analysis/unmitigated-swings`
  - `/gold-strategy/*`
  - `/continuation-failure/*`
- Deleted the legacy backend strategy modules and market-structure analytics files that powered those features.

## Added

- Added `apps/backend-python/app/services/trap_reversal_automation.py`.
- Added a thread-safe singleton `TrapReversalManager` with `O(1)` symbol routing into per-symbol `DoubleTrapFSM` instances.
- Added H1 structural indexing via `scipy.signal.find_peaks` plus a forward-pass monotonic stack to keep only unmitigated supports and resistances.
- Added the new backend routes:
  - `POST /trap-reversal/start`
  - `POST /trap-reversal/stop`
  - `GET /trap-reversal/levels/{symbol}`
  - `GET /trap-reversal/active`
- Added `apps/frontend-react/src/pages/TrapReversalDashboard.jsx` as the new command center UI.

## Architecture

- Live tick processing in `market_data_stream.py` now routes strategy work only into the trap-reversal manager instead of the removed GOLD and Continuation Failure runtimes.
- Live websocket snapshots no longer include legacy strategy payloads; the trap-reversal dashboard polls its own REST summaries so the `/ws/live` path stays focused on prices, watchlists, orders, and notifications.
- Header personalization now treats `trap-reversal` as the only dedicated strategy destination alongside Trading, Positions, Trade Planner, and Admin.
