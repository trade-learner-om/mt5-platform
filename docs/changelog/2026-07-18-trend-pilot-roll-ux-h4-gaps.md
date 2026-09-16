# Trend Pilot roll UX, always-in-position, H4 gap fix

## Summary

- Backtest H4 candles load from range start (`get_backtest_h4_candles`) so roll timestamps advance every 4 hours instead of clustering at range edges.
- After first entry, backtest engine enforces always-in-position until backtest end close.
- `H4_WINDOW_ROLL` rows include `position_side`, `entry_price`, `h4_close`, `updated_sl`, `running_pnl`, and `quantity`.
- Roll list UI shows H4 close date, side, updated SL, and running P/L on the row header (no expand clutter).

## Files

- `apps/backend-python/app/services/candle_history.py`
- `apps/backend-python/app/services/metaapi_client.py`
- `apps/backend-python/app/main.py`
- `apps/backend-python/app/services/trend_pilot_backtest.py`
- `apps/frontend-react/src/components/trend-pilot/TrendPilotRollRow.jsx`
- `apps/backend-python/test_trend_pilot_backtest.py`
- `docs/skills/automation.md`
