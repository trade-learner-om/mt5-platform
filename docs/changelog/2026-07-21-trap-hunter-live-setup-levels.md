# Trap Hunter live setup levels

## Summary

Live Trap Hunter runs now expose per-side setup levels in the runtime snapshot and display them on the active run card.

## Backend

- `TrapHunterSideEngine.snapshot_levels()` returns sweep level, trap phase, R1 OHLC, armed order levels, and open position management levels.
- `TrapHunterRunner.snapshot()` adds `short_levels`, `long_levels`, `forming_m5`, and `h4_time`.

## Frontend

- `TrapHunterActiveRunCard` shows H4 short/long watch levels, per-side setup panels, forming M5 OHLC, armed order brackets, and open position targets.
- Live gold price shown in the active run card header (from websocket ticks, with backend bid fallback).
- M5 countdown uses `MM:SS` and clamps invalid server close times to the current 5-minute window.
