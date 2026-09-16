# Trend Pilot C1–C9 flow alignment

## Summary

Aligned Trend Pilot backtest and live runtime with the canonical rolling 2-candle H4 trailing-stop flow, added a golden C1–C9 regression test, and surfaced P/L on roll row headers.

## Changes

- **Backtest engine**: reversal triggers use stored `position.stop_loss`; H4 window rolls emit `unrealized_pnl` at each closed candle.
- **Live runtime**: track `position_stop_loss` / `position_entry_price`; reversal and H4 roll events include P/L fields.
- **Golden test**: `test_canonical_c1_c9_long_trail` asserts single LONG entry at 3997 and SL trail 3950 → 4047.
- **UI**: `TrendPilotRollRow` shows end-of-candle unrealized P/L on H4 rolls and realized leg P/L on trade closes in the row header.
- **Docs**: canonical C1–C9 example and trailing-SL semantics in `docs/skills/automation.md`.
