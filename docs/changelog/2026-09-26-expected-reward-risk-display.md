# Expected profit/loss on SL+Target orders

Orders that have a known stop loss, target, and risk amount now show an **Exp** value as `reward/risk` (example: `200/80`).

Shown on:

- Open positions
- Deferred market-closed pending orders
- Open / stop / conditional order tables (when SL+Target+risk are present)
- Place Order preview

Calculation: `round(risk_amount × rr_ratio) / round(risk_amount)`. Missing target or risk shows `—`.
