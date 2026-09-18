# Master Break

## Purpose

Document Master Break: international XAUUSD/GOLD dual-side break strategy with live FSM and backtest.

## Implementation

| Concern | Path |
|---------|------|
| Live manager | `apps/backend-python/app/services/master_break_runtime.py` |
| FSM | `apps/backend-python/app/services/master_break_fsm.py` |
| Levels / settings / risk | `master_break_levels.py`, `master_break_settings.py`, `master_break_risk.py` |
| Persistence | `master_break_persistence.py` |
| Backtest | `master_break_backtest.py`, `master_break_backtest_persistence.py`, `master_break_backtest_analytics.py` |
| UI | `apps/frontend-react/src/pages/MasterBreakDashboard.jsx` |

Settings persist in `users.ui_settings.master_break`. Results live in `strategy_results` with `strategy_type=master_break`. Startup restore reloads `RUNNING` docs from `master_break_runs` before market streams resume.

Live ticks share `market_data_stream` with trap reversal via `master_break_manager.handle_price`.

## Level and arming rules

- Master level uses the **latest completed** master candle only: short = bar **high**, long = bar **low** (any color).
- Masters activate at **close** (bucket open + TF). While waiting for break, each newly completed master replaces the level.
- Exec needs a close beyond the level, then a red (short) / green (long) signal candle to arm a sell/buy **stop**.
- Fill only on a **later** exec bar (`low`/`high` vs entry). Backtest trade count includes **fills** only.
- Candle times are **broker server faces** (naive; no IST/EEST conversion, no `astimezone` face shifts).
- Multi-target partials + breakeven after fill; no SL-hit retry in backtest.
- H6/H12 aggregated from native MT5 H1 with inferred open phase (EEST/`xx:00` brokers → phase 0 → masters at `00/06/12/18`). Force-refresh aggregated TF caches on each backtest.

## REST

- `POST /master-break/start`
- `POST /master-break/stop`
- `GET /master-break/active`
- `GET/PUT /master-break/settings`
- `POST /master-break/backtest`
- `GET /master-break/backtests`
- `GET /master-break/backtest/{id}`
- `DELETE /master-break/backtest/{id}`
- `GET /master-break/backtest/{id}/trades`

## Frontend

Live / Backtest / History tabs with settings gear modal. Details panels show expandable `master_rows` audit (per completed master candle) with copy-raw-JSON helpers — not a primary trade list.

## Related

Scheduled Break Trade is a separate user-level tool — see `docs/skills/scheduled-break-trade.md`. Do not conflate the two.
