# Swings tab and refined market structure

## Added

- New **Swings** web tab (international MT5 only) with instrument search, timeframe selection (5m, 15m, 1h, 4h, Daily), and **Analyze Market Structure** action.
- Backend analytics module `apps/backend-python/app/services/analytics/market_structure.py` implementing the 3-layer pipeline:
  1. 11-bar fractal candidates with ATR(14) 2× confirmation and recursive provisional swing updates
  2. 20-period volume SMA + 1.5σ institutional filter
  3. Liquidity sweeps, fair value gaps (with mitigation tracking), and order blocks with optional LTF CHoCH confirmation
- `POST /analysis/market-structure` API returning swings, sweeps, FVGs, order blocks, and progress logs.
- TradingChart overlay support for structure price lines and swing markers on the Swings page.

## Removed

- Deprecated `POST /analysis/h1-swings` and its H1-only Mongo candle helpers (replaced by the multi-timeframe market structure engine using the shared chart candle cache).

## Tests

- `apps/backend-python/test_market_structure.py` — synthetic DataFrame coverage for volume filter, FVG mitigation, sweeps, and progress logging.
