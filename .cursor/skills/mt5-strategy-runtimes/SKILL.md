---
name: mt5-strategy-runtimes
description: >-
  Trap Reversal, Master Break, and Scheduled Break Trade strategy runtimes.
  Use when editing FSMs, strategy REST routes, dashboards, backtests, or live
  tick routing into strategy managers.
---

# Strategy Runtimes

Read first:

1. `docs/skills/automation.md` (index + removed routes)
2. Matching skill: `trap-reversal.md`, `master-break.md`, or `scheduled-break-trade.md`

Shared tick hub: `apps/backend-python/app/services/market_data_stream.py`.

Do not restore `/gold-strategy/*`, `/trend-pilot/*`, `/trap-hunter/*`, or other removed families.
