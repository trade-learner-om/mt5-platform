# EMA Wakeup / Action Candle backtest (XAUUSD M5)

> **Superseded:** entry/exit rules were replaced by SS/Hammer dual-side logic on 2026-08-12. See [`2026-08-12-ema-wakeup-ss-hammer.md`](./2026-08-12-ema-wakeup-ss-hammer.md). APIs and UI shell remain.

## What shipped

Backtest-only strategy: EMA(20) wakeup candle → later action candle → pending stop, one SL retry, better-setup switch, two-tier R exits.

### Rules (summary)

- **Long WC**: prior close ≤ EMA, close > EMA. **AC** (not necessarily next bar): open and close > EMA.
- Cancel WaitAC / pending if close ≤ EMA. Entry = AC high + 1pt, SL = AC low − 3pt.
- **Short** mirrors: WC/AC below EMA; cancel on close ≥ EMA; entry = AC low − 1pt, SL = AC high + 3pt.
- One retry after SL (same prices). Better AC with tighter range replaces pending.
- Exits: Tier1 `% @ R` (default 50% @ 4R), remainder `@ R` (default 8R).

### APIs

- `POST /ema-wakeup/backtest`
- `GET /ema-wakeup/backtests?limit=&cursor=`
- `GET /ema-wakeup/backtest/{id}`
- `GET /ema-wakeup/backtest/{id}/trades?limit=&cursor=`
- `DELETE /ema-wakeup/backtest/{id}`
- `GET`/`PUT /ema-wakeup/backtest/settings`

Saved result `name`: `{yyyyMMMdd}-{yyyyMMMdd}-{risk}-{pnl}` (e.g. `2026Jan01-2026Aug11-100-245.50`).

### UI

Nav **EMA Wakeup** → backtest form with two-tier trade management, named results list, summary stats, cursor-paginated trades.
