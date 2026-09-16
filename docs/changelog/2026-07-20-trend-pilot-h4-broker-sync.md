# Trend Pilot: direct broker H4 window sync

## Problem

H4 window (C1/C2) could stay stale on the dashboard because rolls depended on tick timing, schedulers, overdue guards, and Mongo candle cache that could be gapped. Multiple roll iterations still showed old C1/C2.

## Fix

- `get_fresh_h4_candles()` — always fetch H4 from MT5 on roll/sync (never trust gapped cache)
- `sync_h4_window_from_broker()` — compare stored C1/C2 to broker latest contiguous completed pair; apply window when different
- `GET /trend-pilot/active` — restore run into memory if needed, then sync window from broker every poll (~3s)
- New runs also prime window from fresh MT5 candles

This is the source of truth for what the UI displays.
