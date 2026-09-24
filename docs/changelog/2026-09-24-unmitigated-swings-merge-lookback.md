# 2026-09-24 - Unmitigated swings 1% merge + lookback expand

## Changed

- Analyze merges swing highs/lows within **1%** (keep extreme of each cluster).
- Candle lookback expands 500 → 1000 → 2000 → 4000 → 5000 until `swing_count` highs and lows are filled (or broker history is exhausted).
- Response includes `lookback_exhausted`; UI shows a short note when fewer than requested swings remain.
