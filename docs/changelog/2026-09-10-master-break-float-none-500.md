# Fix Master Break backtest float(None) 500

## Summary

Hardened numeric coercion (`as_float`) for broker point, OHLC, risk sizing, and arm payloads so `None` from sparse MT5 symbol specs no longer raises `TypeError: float() argument ... NoneType` during backtest simulation.
