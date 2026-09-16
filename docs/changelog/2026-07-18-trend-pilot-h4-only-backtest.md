# Trend Pilot H4-only backtest

## Summary

Refactored the Trend Pilot backtest engine to replay H4 candles directly with close-based entry and stop triggers at calculated buffered prices, removing the M1 dependency that caused date gaps in roll history.

## Changes

- **Backtest engine**: loops H4 bars only; entry when `close >= long_entry` (or `close <= short_entry`); reversal when `close` crosses stored SL; fills at calculated buffered prices.
- **Candle loading**: `_load_trend_pilot_backtest_candles` fetches H4 only (no M1 fetch or 5000-bar cap).
- **Roll timestamps**: each `H4_WINDOW_ROLL` `event_time` is the closed H4 bar time (consecutive 4-hour spacing).
- **Tests**: golden C1–C9 and all backtest tests use H4-only fixtures.
- **UI**: H4 roll headers show running P/L (`running_pnl`); backtest roll lists scroll so expanded bottom rows stay visible.
- **Docs**: H4-close backtest semantics documented in `docs/skills/automation.md`.
