# Scheduled Break Trade

## Purpose

Watch an M1/M5/M15 close past a user level, arm on the next valid red/green candle, place an SL (with primary SL→LIMIT fallback on Invalid price), optionally re-place the same SL once after a clean stop-out, and persist the full primary + `RETRY_*` lifecycle on one `scheduled_trades` document.

## Routes

- `POST /scheduled-trades` — create schedule on the selected international account
- `GET /scheduled-trades` — list schedules for the selected account
- `POST /scheduled-trades/{id}/cancel` — cancel while cancellable
- `GET /scheduled-trades/{id}/events` — schedule event log

Live snapshot field: `scheduled_trades` on `/ws/live`.

## Status lifecycle

Primary: `INITIATED` → `ARMED` → `ORDER_PLACED` → `ORDER_FILLED` → `TARGET_EXIT` | `STOP_EXIT` | `USER_EXIT` | `CANCELLED`

Retry (same document, when `retryable_order=true`): `STOP_EXIT` → `RETRY_INITIATED` → `RETRY_ORDER_PLACED` → `RETRY_ORDER_FILLED` → `RETRY_*_EXIT` | `RETRY_CANCELLED`

v1 retry places the **identical SL immediately** after stop-out (no second candle wait). `RETRY_ARMED` is reserved.

## Placement

| Leg | Order type | Invalid price |
|-----|------------|---------------|
| Primary | SL first via `place_pending_order_with_limit_fallback` | Fall back to LIMIT at same entry/SL/qty/target |
| Retry | SL only via `place_pending_order` | No LIMIT fallback; surface error on schedule |

Signal candles larger than `max_signal_candle_pips` are skipped (`SIGNAL_CANDLE_SKIPPED`) until a valid candle appears. Defaults: **10** FX pips, **100** XAU/GOLD. Create payload / schedule field: `max_signal_candle_pips`.

## Candle source

Live ExecCandle rolls use **bid** (same as Master Break / MT5 charts), not mid. Chart seed candles at create remain bid-based from MT5 history.

## Lifecycle logging

`scheduled_trade_runtime` emits INFO logs for: level break (close above/below user level), green/red signal (and wait/oversized skip), SL placed, LIMIT fallback, placement failure, fill, and TARGET/STOP (or other) exit. Grep `Scheduled trade` in backend logs.

## UI

Root sidebar → **Scheduled Trade** (`ScheduledTradePanel`): create form (Retryable order default **off**) + lifecycle list. Page id: `scheduled-trade`. Notes prefer `last_error` when set.

**Unmitigated Swings** (`unmitigated-swings`) can batch-create schedules with `source=unmitigated_swings`, always `retryable_order=false`, execution TF **M1**. On level break the structure session marks that high/low **Mitigated**. At place time, TP is the farther of 4R vs the prior structure-TF candle extreme (BUY high / SELL low). Routes: `/structure/unmitigated-swings*`.

## Implementation

- Levels/helpers: `apps/backend-python/app/services/scheduled_trade_levels.py`
- Runtime: `apps/backend-python/app/services/scheduled_trade_runtime.py`
- Tick wiring: `market_data_stream` primary tick + post-reconcile sync
- Frontend: `apps/frontend-react/src/components/scheduled-trade/ScheduledTradePanel.jsx`
