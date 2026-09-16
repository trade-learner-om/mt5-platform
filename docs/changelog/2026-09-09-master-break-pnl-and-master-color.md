# Master Break: drop master color filter + fix backtest PnL

## Changes

- Master setup no longer requires two consecutive green (short) / red (long) candles. Any two completed master bars set **C2H** / **C2L**. Exec RC/GC rules unchanged.
- Backtest PnL now uses `pnl_from_fill` → `calc_pnl_from_price_move` with the same `contractSize` / gold pip path as `quantity_from_risk`, instead of `price_move × lots × tickValue`.

## Files

- `master_break_fsm.py`, `master_break_risk.py`, `master_break_backtest.py`, `main.py` backtest route
- Unit tests + `docs/skills/automation.md`
