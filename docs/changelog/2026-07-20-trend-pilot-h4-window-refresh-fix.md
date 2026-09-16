# Trend Pilot H4 window refresh fix

## Summary

- Trend Pilot live H4 window refresh no longer logs a stack trace on every tick when the candle cache returns fewer than two bars.
- `_load_trend_pilot_h4_candles` now uses `get_recent_chart_candles`, which falls back to a direct MT5 fetch when cache/range filtering is sparse.

## Backend

- `get_recent_chart_candles` in `candle_history.py` ensures at least `min_bars` recent candles.
- `handle_price` skips window roll when fewer than two H4 candles are available instead of raising through the generic exception handler.
