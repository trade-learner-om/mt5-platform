# 2026-09-24 - Unmitigated swing detector (library + trap wiring)

## Added

- Restored `apps/backend-python/app/services/analytics/` as a library package (no public analysis routes).
- `market_structure.py`: fractal `detect_swing_pivots`, forward mitigation in `calculate_unmitigated_levels`, optional ATR bar-range filter, ATR-adaptive lookback, and volume gate using `SMA + sigma * STD`.
- Candle helpers: `unmitigated_levels_for_candles`, `unmitigated_supports_resistances_for_candles`, `get_unmitigated_levels_for_symbol` in `candle_history.py`.

## Changed

- Trap Reversal `index_h1_levels` now uses the unmitigated swing detector instead of `scipy.signal.find_peaks`.
- Focused unit tests in `test_unmitigated_swings.py` / `test_market_structure.py`.

## Not restored

- `POST /analysis/unmitigated-swings` and `POST /analysis/market-structure` remain removed per `docs/skills/automation.md`.
