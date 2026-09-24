# 2026-09-25 - Unmitigated swings automation tracking

## Changed

- Session GET/execute responses enrich each swing level with linked schedule fields: `trade_status`, entry/SL/TP, qty, order id, errors.
- Unmitigated Swings page shows an **Automation tracking** table after Execute, polled every few seconds and overlaid with `/ws/live` `scheduled_trades` when available.
