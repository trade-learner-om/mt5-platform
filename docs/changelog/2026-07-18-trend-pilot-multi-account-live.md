# Trend Pilot multi-account live runs

## Summary

- Live start/stop accepts `account_ids` to run Trend Pilot on multiple international MT5 accounts in parallel.
- Each account+symbol pair gets its own FSM key; ticks route per account from the market data stream.
- Dashboard adds a multi-select account picker for Live mode and lists all active runs with account labels.

## Files

- `apps/backend-python/app/main.py`
- `apps/backend-python/app/schemas.py`
- `apps/backend-python/app/services/trend_pilot_runtime.py`
- `apps/backend-python/app/services/trend_pilot_persistence.py`
- `apps/backend-python/app/services/market_data_stream.py`
- `apps/frontend-react/src/pages/TrendPilotDashboard.jsx`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotBacktestRow.jsx`
- `apps/frontend-react/src/App.jsx`
- `docs/skills/automation.md`
