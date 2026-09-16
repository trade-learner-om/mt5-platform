# 2026-09-10 — Scheduled Break Trade

Added a dedicated Scheduled Break Trade flow under Positions.

## Backend

- New `scheduled_trades` / `scheduled_trade_events` collections and `/scheduled-trades/*` routes.
- Runtime FSM on live ticks (M1/M5/M15 bar roll): level break → arm → valid red/green → place SL.
- Primary placement uses SL→LIMIT fallback on Invalid price; optional one-shot retry places SL only.
- Linked order fills/exits/cancels update primary and `RETRY_*` statuses; live WS includes `scheduled_trades`.

## Frontend

- New **Scheduled Trade** tab with create form (Retryable order default off) and lifecycle list.

## Tests / docs

- Unit tests for direction, candle size, entry/SL, LIMIT fallback, and SL-only retry.
- Skill note: `docs/skills/scheduled-break-trade.md`.
