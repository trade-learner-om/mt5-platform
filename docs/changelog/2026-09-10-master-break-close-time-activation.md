# Fix Master Break backtest master close timing

## Summary

Backtest now activates each master candle only after `open + TF` (close time), so an H6 00:00–06:00 high/low stays active for M5 from 06:00 instead of being replaced by the next H6 at its open. Pending fills use STOP semantics and only on a subsequent exec bar after the signal candle.
