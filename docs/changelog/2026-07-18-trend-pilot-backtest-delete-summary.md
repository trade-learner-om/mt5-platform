# Trend Pilot backtest delete + analytics summary

## Summary

- Added `DELETE /trend-pilot/backtest/{result_id}` to remove stored backtest results.
- Backtest summary now includes closed trades, max drawdown, max profit/loss, win/loss streaks, and max DD duration (from/to).
- Backtest UI shows a summary grid when expanded and a Delete button on each result row.

## Files

- `apps/backend-python/app/services/trend_pilot_backtest_analytics.py`
- `apps/backend-python/app/services/trend_pilot_backtest.py`
- `apps/backend-python/app/services/trend_pilot_backtest_persistence.py`
- `apps/backend-python/app/main.py`
- `apps/backend-python/test_trend_pilot_backtest_analytics.py`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotBacktestSummary.jsx`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotBacktestRow.jsx`
- `apps/frontend-react/src/pages/TrendPilotDashboard.jsx`
