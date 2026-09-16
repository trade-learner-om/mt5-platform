# Trap Hunter T1 at configurable R

## Summary

- Replaced fixed `$20` T1 (and H4 high/low cap) with `t1_r_multiple` (default **2R**).
- T1 price = `entry ± (t1_r_multiple × one_r)`.
- Existing `t1_partial_qty_pct` still controls what % is booked at that R (`0` = SL to breakeven only).

## Settings

- New field `t1_r_multiple` (0.5–20) in Trap Hunter settings modal, API, live runs, and backtest snapshots.
- Live run card shows “T1 at XR” next to partial %.
