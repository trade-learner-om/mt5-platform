# Master Break: default H6/H12 open offset 30 minutes

## Summary

MT5 `copy_rates` for FundedNext returns H1 at `xx:00`, so phase inference alone kept masters at `00/06/12/18`. Master Break now defaults `master_open_offset_minutes=30` and passes that phase into H6/H12 aggregation so audit rows open at `xx:30`.

## Changes

- Settings + schemas + settings modal field
- `get_backtest_candles` / `get_fresh_candles` accept `phase_seconds`
- Unit test: `:00` H1 + override 1800 → H6 at `:30`
