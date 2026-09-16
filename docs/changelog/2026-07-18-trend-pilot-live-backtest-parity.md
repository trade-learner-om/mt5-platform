# Trend Pilot live/backtest parity

## Summary

- Live uses 2× reversal pending stops for always-in-position flips; H4 rolls cancel/replace the stop at `updated_sl`.
- Adverse gap-through-SL fallback: cancel limit/stop and market 2× opposite.
- Funded-account loss cap (live only): exit at 0.95% leg loss and re-enter same side.
- Unified roll event schema, live history analytics/summary, and dashboard parity with backtest rows.

## Files

- `apps/backend-python/app/services/trend_pilot_runtime.py`
- `apps/backend-python/app/services/trend_pilot_roll_events.py`
- `apps/backend-python/app/services/trend_pilot_persistence.py`
- `apps/backend-python/app/schemas.py`
- `apps/backend-python/app/main.py`
- `apps/frontend-react/src/pages/TrendPilotDashboard.jsx`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotBacktestRow.jsx`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotRollRow.jsx`
- `docs/skills/automation.md`
