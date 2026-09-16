# Trap Hunter trade details broker time display

## Summary

Roll timestamps in Trap Hunter trade details (backtest modal and live history trades) now display **broker server time** using the account's `broker_utc_offset`, matching the FundedNext/MT5 chart clock.

Summary panel max drawdown times remain in IST (unchanged).

## Changes

- API: `broker_utc_offset` and `broker_time_region` on backtest detail, trade detail, and live run history responses.
- UI: `TrapHunterRollRow` uses `formatBrokerTimestamp`; column header shows broker timezone label.
