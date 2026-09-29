# Automation

## Purpose

Index of strategy runtimes. There are **no active strategy or FSM runtimes**.

## Removed — do not revive

These route families and their UI, services, and FSMs have been deleted:

- `/trap-reversal/*`
- `/master-break/*`
- `/scheduled-trades/*`
- `/structure/unmitigated-swings*`
- `/indian/strategy/preview`, `/indian/pe-cycle/*`
- `/automation/reversal-5m/*`
- `/analysis/market-structure`, `/analysis/unmitigated-swings`
- `/gold-strategy/*`, `/continuation-failure/*`, `/trend-pilot/*`
- `/st-ema/*`, `/ema-vwap/*`, `/ema-wakeup/*`, `/st-rsi-div/*`, `/trap-hunter/*`

Keep order placement, manual order runtime, trade planner, risk sizing, and watchlists.

## Shared tick path

Live ticks still flow through `apps/backend-python/app/services/market_data_stream.py` for watchlist prices, manual orders, deferred market-open orders, and trade planner execution. Candle loading, symbol specs, risk sizing, and pending orders go through the local MT5 adapter (`docs/skills/mt5-integration.md`).
