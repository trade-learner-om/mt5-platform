# Trend Pilot H4 close entry (live)

## Summary

- Live ARMED runs now evaluate H4 close-based entry before rolling the window, matching backtest semantics.
- On H4 close, the just-closed candle is checked against the **pre-roll** C1/C2 buffered entry; if close crossed the level, the runtime market-enters at the calculated entry price, then rolls the window and re-arms (or trails SL if entered).
- Hardened `_on_h4_close` to require 3+ bars, use `window_from_completed_pair` for rolls, and catch window math failures with retry scheduling.

## Impact

- Fixes missed entries when an H4 candle closes through the buffered level but broker stops did not fill (stale levels, gaps, or close-only breach).
- Window still rolls to new C1/C2 after each H4 close; pre-roll entry uses the previous window, roll uses the latest two completed candles.
