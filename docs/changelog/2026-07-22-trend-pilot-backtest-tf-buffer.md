# Trend Pilot backtest timeframe and buffer settings

## Changed

- Trend Pilot backtest settings now include `timeframe` (`M15`, `H1`, `H4`, `D1`) and `price_buffer_usd`.
- Default buffers by timeframe: M15 = $3, H1 = $5, H4 = $10, D = $20.
- Changing timeframe in the settings modal auto-fills the default buffer; the user can override before save.
- Backtest candle loading and replay use the selected timeframe (8-bar warmup) and configured buffer.
- Saved backtest results snapshot `timeframe` and `price_buffer_usd` in `backtest_settings` / summary.
- Live Trend Pilot runtime is unchanged (H4, $10 buffer).

## Tests

- `apps/backend-python/test_trend_pilot_backtest.py`
