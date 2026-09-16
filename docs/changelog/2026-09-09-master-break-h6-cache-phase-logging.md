# Master Break: bust stale H6 cache + phase logging

## Summary

Phase-aligned H6 aggregation was skipped because Mongo still held pre-fix `:00` bars and `_has_coverage` short-circuited the fetch. Aggregated TFs now always re-fetch/re-aggregate, delete the in-range cache, then upsert. Added logging for H1 sample times, inferred phase, aggregate opens, and cache refresh.

## Changes

- `delete_cached_candles` + force refresh for H6/H12/M45 in `get_backtest_candles`
- Logging in phase infer, aggregate, range-fetch, backtest load, Master Break route
