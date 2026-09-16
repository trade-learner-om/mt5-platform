# Master Break: fix H6/H12 backtest candle fetch

## Summary

H6/H12 backtests were calling `copy_rates_from` (bars before range start), so the in-range cache stayed empty and Master Break raised “Not enough candles.” Aggregated TFs now range-fetch the source TF (H1) and aggregate into the requested window.

## Changes

- `candle_history._fetch_mt5_candles_range` + `get_backtest_candles` uses it for H6/H12/M45
- Master Break gate error includes master/exec counts
- Unit tests for H6 aggregation and range-path wiring
