# Automation

## Purpose

Document the dedicated strategy runtimes in the MT5 platform: **Double Trap Reversal** and **Master Break**.

## Implementation

Legacy strategy runtimes for Swings, GOLD Strategy, Continuation Failure, Trend Pilot, ST-EMA, EMA-VWAP, EMA-Wakeup, ST-RSI-DIV, and Trap Hunter have been removed from both the backend and web frontend. Do not add new work to the deleted strategy files or the removed `/analysis/market-structure`, `/analysis/unmitigated-swings`, `/gold-strategy/*`, `/continuation-failure/*`, `/trend-pilot/*`, `/st-ema/*`, `/ema-vwap/*`, `/ema-wakeup/*`, `/st-rsi-div/*`, or `/trap-hunter/*` route families.

Trap Reversal lives in `apps/backend-python/app/services/trap_reversal_automation.py`.
Master Break lives under `apps/backend-python/app/services/master_break_*.py`.

## Double Trap Reversal

The trap-reversal engine is designed for fast local-MT5 execution with minimal tick-path overhead.

- H1 structural supports and resistances are indexed once per start command using `scipy.signal.find_peaks`.
- A forward-pass monotonic stack removes already-mitigated H1 levels before the live engine starts.
- Live routing is `O(1)` from `market_data_stream.py` into `TrapReversalManager.handle_price(symbol, tick)`.
- Each live symbol runs a dedicated `DoubleTrapFSM` that processes scalar prices and a tiny rolling M1 candle buffer rather than pandas dataframes on the tick path.

### FSM sequence

- `SEEKING_H1_SPIKE`
- `WAITING_FOR_FIRST_PULLBACK`
- `WAITING_FOR_TRAP_DROP`
- `TRACKING_TRUE_CHOCH`
- `WAITING_FOR_BREAKOUT`
- `EXECUTION`

### Execution behavior

- Long setups use the current absolute low minus one broker point for stop loss.
- Volume is sized with the existing broker-aware risk utilities and MT5 symbol specifications.
- Entries are sent as pending `BUY LIMIT` orders through the local MT5 compatibility adapter.
- The nearest active H1 resistance above the entry becomes the target.

### REST Surface

- `POST /trap-reversal/start`
- `POST /trap-reversal/stop`
- `GET /trap-reversal/levels/{symbol}`
- `GET /trap-reversal/active`

### Frontend

The web command center for trap reversal lives in `apps/frontend-react/src/pages/TrapReversalDashboard.jsx`.

- The left panel proves the active H1 supports/resistances being hunted.
- The right panel polls current FSM summaries across active symbols.

## Master Break

Master Break is international MT5 only and restricted to XAUUSD/GOLD.

- Settings (`risk_amount`, master/exec timeframes, `breakeven_r`, multi-target `qty_pct` summing to 100) persist in `users.ui_settings.master_break`.
- Master level uses the **latest completed** master candle only: short = that bar’s **high**, long = that bar’s **low** (any color). Masters activate at **close** (bucket open + TF), so M5 after an H6 00:00–06:00 close trades that high/low until the next H6 closes. While waiting for break, each newly completed master replaces the level. Exec needs a close beyond the level, then a red (short) / green (long) signal candle to arm a sell/buy **stop**; fill only on a **later** exec bar (`low`/`high` vs entry). Backtest trade count only includes **fills** (armed-but-unfilled setups are not trades). Candle times stay **broker server faces** (naive; no IST/EEST conversion and no `astimezone` face shifts).
- Live: dual-side FSMs seed from master + exec candles, then consume ticks from `market_data_stream` via `master_break_manager.handle_price`.
- Backtest: loads master + exec candles through `get_backtest_candles`, simulates fills/partials/BE (no SL-hit retry), sizes with `quantity_from_risk`, and values PnL with `calc_pnl_from_price_move` (aligned with qty — not `tickValue × price`). Results store in `strategy_results` with cursor-paginated history/trades. Detail payloads include `master_rows`: one audit row per completed master candle in the requested window (no in-range skips), with SHORT/LONG side fields and clipboard-only raw JSON in the UI. H6/H12 are aggregated from native MT5 H1 with **inferred open phase** (EEST/`xx:00` brokers → phase 0 → masters at `00/06/12/18`). Do not reinterpret broker faces via machine-local TZ (IST). Aggregated TF caches are force-refreshed on each backtest.
- Startup restore reloads `RUNNING` docs from `master_break_runs` before market streams come back.

### REST Surface

- `POST /master-break/start`
- `POST /master-break/stop`
- `GET /master-break/active`
- `GET/PUT /master-break/settings`
- `POST /master-break/backtest`
- `GET /master-break/backtests`
- `GET /master-break/backtest/{id}`
- `DELETE /master-break/backtest/{id}`
- `GET /master-break/backtest/{id}/trades`

### Frontend

`apps/frontend-react/src/pages/MasterBreakDashboard.jsx` provides Live / Backtest / History tabs with a settings gear modal and shared cursor pagination helpers. Backtest/History **Details** panels show expandable master-candle audit rows (not a primary trade list), with per-row and bulk **Copy raw JSON**.

## Local MT5 Notes

Historical candle loading, symbol specifications, risk context, and pending-order placement all continue to flow through the local MT5 backend adapter rather than MetaApi.cloud.
