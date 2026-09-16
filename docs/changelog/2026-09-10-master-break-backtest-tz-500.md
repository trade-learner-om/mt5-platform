# Fix Master Break backtest 500 on timezone compare

## Summary

Hardened candle/trade timestamp coercion to always-aware UTC so close-time master activation never compares naive vs aware datetimes. Summary analytics now parses unix ints and mixed timestamps safely. Backtest route logs and returns the real simulation error message on failure.
