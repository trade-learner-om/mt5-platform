# Trap Hunter Backtest/Live Parity

## Summary

- Replaced manual quantity input with risk-based position sizing for Trap Hunter live runs and backtests.
- Fixed live bracket order placement (correct MetaAPI args and `orderId` parsing).
- Added intrabar trap detection on forming M5 candles with immediate SL bracket placement.
- Aligned FSM to process pending SL/fill checks on the same bar after R1 arm.
- Added live H4 anchor rolling to match backtest H4_ANCHOR behavior.
- Pending broker orders are cancelled and replaced when R1 shifts.

## UI (2026-07-21)

- Trap Hunter expanded backtest row: summary panel stays fixed at top; only the trades list scrolls.

## API changes

- `TrapHunterStartIn.quantity` → `risk_amount`
- `TrapHunterBacktestIn.quantity` → `risk_amount`
- Backtest results store `risk_amount`; per-trade `quantity` is computed at entry.
