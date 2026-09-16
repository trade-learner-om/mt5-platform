# Trend Pilot backtest

## Added

- `apps/backend-python/app/services/trend_pilot_backtest.py` — isolated M1 replay simulator with H4 window rolls, reversal rolls, P/L updates, and SL changes.
- `apps/backend-python/app/services/trend_pilot_backtest_persistence.py` — `strategy_results` collection writes filtered by `strategy_type: "trend_pilot"`.
- REST routes: `POST /trend-pilot/backtest`, `GET /trend-pilot/backtests`, `GET /trend-pilot/backtest/{result_id}`.
- Frontend Live | Backtest tabs on `TrendPilotDashboard.jsx` with expandable `TrendPilotBacktestRow` roll history.

## Isolation

- No changes to `trap_reversal_automation.py` or `manual_order_runtime.py`.
- Backtest results are stored only in `strategy_results` with `strategy_type: "trend_pilot"`.

## Tests

- `apps/backend-python/test_trend_pilot_backtest.py`
