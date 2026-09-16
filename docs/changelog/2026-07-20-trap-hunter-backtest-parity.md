# Trap Hunter backtest parity with Trend Pilot

## Summary

Trap Hunter backtests now persist one run-level document in `strategy_results` (`strategy_type: trap_hunter`) in addition to per-trade rows in `trap_hunter_trades`. The dashboard shows the same summary grid as Trend Pilot, Mongo-backed cursor pagination at the bottom of the results list, dark-mode-safe expanded rows, and a collapsible raw JSON inspector.

## Backend

- Added `trap_hunter_backtest_persistence.py` for save/list/detail/delete against `strategy_results`.
- Extended `trap_hunter_backtest_analytics.py` with `flatten_trade_rolls` and `compute_backtest_analytics` (max profit/loss, streaks, drawdown window/duration, plus short/long trap stats).
- `POST /trap-hunter/backtest` saves the run document first, then persists trade drill-down rows with a shared `backtest_id`.
- List/detail/delete endpoints read from `strategy_results`; delete removes both the run document and linked trades.

## Frontend

- `TrapHunterBacktestSummary` mirrors Trend Pilot summary fields and adds trap-specific short/long stats.
- Expanded backtest rows show Summary → Trades → Raw JSON (`<details>`).
- Pagination moved to the bottom with `disabled={isFetching}` while pages load.
- Dark-mode and horizontal overflow fixes on trade/roll rows.

## Notes

- Legacy backtests created before this change (trade rows only, no `strategy_results` doc) will not appear in the paginated list until re-run.
