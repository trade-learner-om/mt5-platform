# Automation

## Purpose

Index of **active** strategy runtimes. Prefer the dedicated skill files when editing one strategy.

## Active runtimes

| Runtime | Skill | Code |
|---------|-------|------|
| Double Trap Reversal | [trap-reversal.md](trap-reversal.md) | `trap_reversal_automation.py` |
| Master Break | [master-break.md](master-break.md) | `master_break_*.py` |
| Scheduled Break Trade (user tool) | [scheduled-break-trade.md](scheduled-break-trade.md) | `scheduled_trade_runtime.py` |

## Removed — do not revive

Legacy strategy runtimes and route families have been deleted from backend and web frontend:

- `/automation/reversal-5m/*`
- `/analysis/market-structure`, `/analysis/unmitigated-swings`
- `/gold-strategy/*`, `/continuation-failure/*`, `/trend-pilot/*`
- `/st-ema/*`, `/ema-vwap/*`, `/ema-wakeup/*`, `/st-rsi-div/*`, `/trap-hunter/*`

Do not add new work to deleted strategy files. Mobile apps may still contain stale clients for GOLD Strategy / Trend Pilot — remove those clients rather than restoring routes.

Allowed replacement for structure swings: `/structure/unmitigated-swings*` (library + Scheduled Break execute path).

## Shared tick path

Live strategies consume ticks from `apps/backend-python/app/services/market_data_stream.py` after local MT5 polling or `WS /ws/mt5/ticks` ingest. Candle loading, symbol specs, risk sizing, and pending orders go through the local MT5 adapter (`docs/skills/mt5-integration.md`).
