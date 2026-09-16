# Session VWAP broker-day reset

## Summary

Session VWAP now resets on the **broker/exchange calendar day** using account `broker_utc_offset` (same convention as broker time display), matching TradingView Session VWAP when the chart timezone aligns with the broker.

## Changes

- `compute_vwap(..., session_offset_seconds=…)` day key = UTC + offset
- EMA Wakeup + EMA–VWAP backtest/runtime pass account offset into VWAP
- `volumes_for_vwap`: prefer tick volume; no synthetic `1.0` mid-session when real volumes exist

## Compare on TradingView

Anchor = Session, Source = hlc3, chart timezone = broker/exchange. Different data vendors can still differ slightly in OHLC/tick volume.
