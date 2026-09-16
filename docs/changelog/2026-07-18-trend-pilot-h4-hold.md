# Trend Pilot hold position through H4 rolls

## Fixed

- Backtest no longer closes and re-enters the same side on each H4 window roll.
- H4 rolls now emit `H4_WINDOW_ROLL` with updated buffered stop loss while keeping LONG/SHORT open.
- Live `apply_window` updates broker stop loss on open positions instead of force-closing on H4 roll.

## Tests

- `test_h4_roll_holds_short_without_duplicate_entries` in `test_trend_pilot_backtest.py`
