# Trap Hunter strategy

## Backend

- Added isolated Trap Hunter runtime with dual FSMs (`SHORT_TRAP` / `LONG_TRAP`) in `trap_hunter_runtime.py`.
- Added M5/H4 backtest engine in `trap_hunter_backtest.py` with per-trade `rolls[]` persisted to `trap_hunter_trades`.
- Added `/trap-hunter/*` routes (start, stop, active, backtest, backtests, trade detail).
- Wired live tick routing in `market_data_stream.py`.
- Added `get_backtest_m5_candles` for historical M5 replay.

## Frontend

- Added `TrapHunterDashboard.jsx` with Trend Pilot-style backtest list, expandable run → trade → roll timeline.
- Added Trap Hunter nav item in `App.jsx`.

## Isolation

- No changes to `trap_reversal_automation.py` or `manual_order_runtime.py`.
