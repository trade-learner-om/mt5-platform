# Trap Hunter R1 arm on completed M5 only

## Summary

- Live forming-M5 path no longer arms or shifts R1 from incomplete candle OHLC.
- Crossed H4 sweep on ticks and ARMED fill / pending-SL handling on forming bars are unchanged.
- R1 entry/SL are taken only from a **completed** M5 trap candle (`on_completed_m5`).

## Why

Arming mid-bar used a partial high/low (e.g. entry 4068.81 / SL 4070.50) before the pin finished (~4073.95 / ~4066.79), so live fills disagreed with the closed chart bar; T1 then moved SL to breakeven at the premature entry.

## Tests

- Forming red after sweep → stays swept, no `ENTRY_ARMED`
- Same bar on complete → arm with entry = low − point, SL = high
