# Trap Hunter H4 anchor and startup breach fix

## Summary

- Backtest H4 anchors now roll only when the H4 bar **closes** (`open + 4h`), removing lookahead that could sweep inside the anchor bar (e.g. Jul 20 00:00 EURUSD long at 02:20 UTC).
- Added **startup-only** side block: if the anchored H4 extreme is already wicked when a run/backtest starts, that side is disabled until the next H4 close.
- **Two consecutive SL hits** per H4 session still disable the side until the next H4 anchor (unchanged).
- Live runs call startup breach check once after initial H4 anchor; UI shows `startup_blocked` separately from 2x SL disable.
- Backtest audit adds checks for anchor close time, sweep after anchor close, and startup block respect.
