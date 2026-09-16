# Trend Pilot backtest 500 import shadow fix

## Summary

- `POST /trend-pilot/backtest` returned **500** because Trap Hunter’s `save_backtest_result` import overwrote Trend Pilot’s in `main.py`.
- Simulation succeeded; save failed with `TypeError: unexpected keyword argument 'quantity'`.

## Fix

- Alias Trap Hunter backtest + run persistence imports so they no longer shadow Trend Pilot helpers.
- Trap Hunter endpoints now call the aliased functions explicitly.
