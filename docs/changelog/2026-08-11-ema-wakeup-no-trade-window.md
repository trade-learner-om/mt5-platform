# EMA Wakeup no-trade window (broker time)

## Summary

EMA Wakeup backtests can skip new entries during a configurable broker-time window. Default is **23:30 → 01:30** (overnight wrap). Open positions still manage SL/target; waits and pending stops are cleared for the window.

## Changes

- Settings / API: `no_trade_from`, `no_trade_to` (`HH:MM`)
- Engine uses account `broker_utc_offset` the same way the UI maps UTC → broker clock
- Dashboard: time selectors labeled “No trade between (broker time)”
- Equal from/to disables the window
