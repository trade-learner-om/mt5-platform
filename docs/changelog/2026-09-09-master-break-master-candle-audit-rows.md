# Master Break: per-master-candle backtest audit rows

## Summary

Backtest Details now list one expandable audit row per completed master candle in the requested range (no in-range skips). Each row carries SHORT/LONG side fields (exec beyond, bias, signal candle, planned entry/SL, fill/exit/pnl). Raw JSON is clipboard-only.

## Changes

- `simulate_master_break_backtest` emits `master_rows` (range-filtered; warmup masters still advance FSM)
- Persist `master_rows` / `master_row_count` on `strategy_results`; detail GET returns them; list API omits the heavy array
- Master Break dashboard Backtest + History Details use `MasterCandleList` with Copy raw JSON
- Unit tests for row count, break/arm/fill fields, and null pnl when unfilled
