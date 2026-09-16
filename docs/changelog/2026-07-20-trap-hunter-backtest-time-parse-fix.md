# Trap Hunter backtest: Unix timestamp candle time fix

## Summary

Trap Hunter backtest failed with `Candle is missing a valid time.` because `get_backtest_h4_candles` / `get_backtest_m5_candles` return candles with Unix integer `time` values via `serialize_chart_candle`, while `_coerce_candle_time` only parsed `datetime` and ISO strings.

## Changes

- `_coerce_candle_time` in `trap_hunter_backtest.py` now accepts int/float epoch seconds (and millisecond epochs).
- Unit test covers integer-timestamp candle fixtures matching the live API path.
