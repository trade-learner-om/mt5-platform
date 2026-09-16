# Trend Pilot backtest timeframe on run + TF-aware roll labels

## Problem

Selecting H1 in backtest settings still looked like H4 because:

1. Run Backtest POST did not send `timeframe` / `price_buffer_usd` (only saved settings applied; default H4).
2. Roll events were always `H4_WINDOW_ROLL` with "H4 close" UI copy.

## Fix

- `TrendPilotBacktestIn` accepts optional `timeframe` and `price_buffer_usd`; request overrides stored settings.
- Dashboard Run Backtest POST sends current settings TF/buffer.
- Simulator emits `WINDOW_ROLL` with TF-aware messages (legacy `H4_WINDOW_ROLL` still accepted in analytics/UI).
- Summary and roll rows show the result timeframe; list items include `timeframe`.
