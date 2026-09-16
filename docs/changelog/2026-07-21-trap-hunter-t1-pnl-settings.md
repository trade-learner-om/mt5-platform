# Trap Hunter T1 P/L and settings modal

## Backend

- Fixed T1 profit booking in `trap_hunter_fsm.py`: `T1_ACHIEVED` now records P/L (~$20 unrealized by default) instead of `$0.00`.
- Breakeven exits after T1 keep the booked T1 profit; trailed exits avoid double-counting.
- Optional `t1_partial_qty_pct` closes that share at T1 and tracks `remaining_quantity`.
- Added `TrapHunterSettings` with `GET/PUT /trap-hunter/settings` persisted under `users.ui_settings.trap_hunter`.
- Live runtime issues broker partial closes at T1 when partial % is enabled and syncs SL via position ticket lookup.
- Analytics streaks now use `SL_HIT` close events only; summary includes `breakeven_trades`.

## Frontend

- Added `TrapHunterSettingsModal` with symbol, risk amount, backtest date range, and T1 partial %.
- Moved all Trap Hunter inputs out of the header into the modal; header shows compact summary chips.

## Tests

- Added T1 breakeven, initial SL, partial-close, and settings unit tests in `test_trap_hunter_backtest.py`.
