# Master Break: fix empty master_rows on unix candle times

## Summary

Production backtest candles use unix int `time` values. `_iso_time` stored them as digit strings (`"1704067200"`), and the final `_in_range` filter failed to parse those strings—so every audit row was dropped and the UI showed “No master candles in range.”

## Changes

- `_iso_time` coerces via `coerce_candle_time` then emits ISO
- `coerce_candle_time` accepts digit-only epoch strings
- Regression test with unix-int candle times
