# EMA Wakeup SS/Hammer rule rewrite

## Summary

EMA Wakeup backtest now uses **Shooting Star (short)** / **Hammer (long)** setups instead of WC/AC, with dual long+short, 3-bar pending expiry, mandatory partial at R with SL→BE, and runner exit on VWAP/EMA close.

## Rules (short; long mirrors)

- Close above VWAP + EMA; SS via existing candle helper; prior two greens (skip range &lt; $1); pattern range $3–$6
- Entry = SS low − 1 tick, SL = SS high + 3 tick; expire after 3 bars; SL re-arms same levels; new setup replaces pending
- Partial `% @ R` then BE; remainder exits when close above both (short) / below both (long)

## UI

Same EMA Wakeup tab: pattern min/max, partial % @ R, no-trade window; trade rows show Setup / EMA / VWAP.
