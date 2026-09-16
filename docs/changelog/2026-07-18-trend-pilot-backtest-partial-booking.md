# Trend Pilot backtest partial booking

## Summary

Added backtest-only partial booking for Trend Pilot with persisted user settings, intrabar partial triggers, breakeven SL handling, and dual-sided re-arm after breakeven exits.

## Backend

- `TrendPilotBacktestSettings` dataclass and partial booking logic in `trend_pilot_backtest.py`
- New roll types: `PARTIAL_BOOK`, `BREAKEVEN_EXIT`
- `GET/PUT /trend-pilot/backtest/settings` persisted in `users.ui_settings.trend_pilot_backtest`
- Backtest results snapshot settings under `strategy_context.backtest_settings`

## Frontend / mobile

- Web backtest settings modal on Trend Pilot dashboard
- Android/iOS backtest settings sheet with the same fields

## Behavior

- Partial triggers on H4 bar high/low touch at calculated trigger price
- After partial + breakeven SL: conflict with C1/C2 SL or later BE stop hit returns to ARMED (both sides), not reversed-side-only entry
- Scaled reversal (`2×` runner) applies only when C1/C2 SL hits without an active breakeven stop
