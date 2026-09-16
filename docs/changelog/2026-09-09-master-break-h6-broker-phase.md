# Master Break: align H6/H12 aggregation to broker H1 phase

## Summary

Synthetic H6/H12 bars no longer floor to epoch-aligned `00/06/12/18`. Aggregation infers the H1 open phase (e.g. FundedNext `xx:30` → phase 1800) and buckets with that offset so master opens match the broker chart.

## Changes

- `_infer_bar_phase` + offset bucket math in `_aggregate_candles`
- Unit tests for `:00` and `:30` H1 → H6 opens
- Automation skill note for inferred H1 phase
