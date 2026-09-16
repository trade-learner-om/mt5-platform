# Trap Hunter H4 sweep mode setting

## Summary

- Added `h4_sweep_mode` to Trap Hunter settings (`crossed` | `closed`, default `crossed`).
- **crossed**: confirms sweep when price trades through the H4 level — live uses bid/ask ticks; backtest uses M5 wick (low/high).
- **closed**: confirms sweep only when the M5 bar closes beyond the level (long: close ≤ level; short: close ≥ level).

## Live

- `on_forming_m5` evaluates crossed sweeps on every tick (bid for long, ask for short).
- Closed mode skips forming-tick sweep; confirmation happens on M5 bar close only.

## UI

- Trap Hunter settings modal includes H4 sweep mode selector (live and backtest).
