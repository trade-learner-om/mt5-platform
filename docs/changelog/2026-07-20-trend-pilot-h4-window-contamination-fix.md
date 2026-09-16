# Trend Pilot H4 window contamination fix

## Summary

- Fixed Trend Pilot arming the H4 window from the forming (running) candle when only two bars were returned from cache.
- `compute_h4_window` now requires three bars (two completed + forming) and always drops the last MT5 bar before selecting C1/C2.
- Live H4 loader requires at least three bars; sparse two-bar cache responses no longer arm with a contaminated window.
- Active runs expose `c1_time`, `c2_time`, `c1_ohlc`, and `c2_ohlc` in snapshots for UI verification.
- Active Run panel redesigned with header strip, stat tiles, H4 window panel, and color-coded long/short level cards.

## Impact

- Example: C1 high 4021 / C2 high 4018 with running high 4028 now arms long entry at **4031** (4021 + $10), not 4038 (running high + $10).
