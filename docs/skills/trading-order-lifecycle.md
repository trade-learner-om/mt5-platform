# Trading Order Lifecycle

## Purpose

Keep the reference workflow for manual orders, copy trading targets, broker reconciliation, order events, and notifications.

## Implementation

Order endpoints live in `apps/backend-python/app/main.py`:

- `POST /orders`
- `POST /orders/{order_id}/modify`
- `POST /orders/{order_id}/cancel`
- `POST /orders/{order_id}/close`
- `POST /orders/{order_id}/defer-market-open`
- `POST /orders/{order_id}/decline-defer`
- `GET /orders/{order_id}/events`
- `GET /orders/history`

Local order records are stored in `orders`; audit events are stored in `order_events`; user activity appears in `notifications`.

## Manual Trade Options

`POST /orders` accepts:

- `retryable_order` (default `true`, honored for `LIMIT` and `SL`)
- `automatic_trade_management` (default `true`)
- `conditional_order` (default `false`, Manual `SL` only) with `trigger_price`

These are persisted on each order in `manual_context`:

- `retryable_order`
- `automatic_trade_management`
- `retry_used`
- `partial_booked_4r`
- `target_booked`
- `position_was_open`
- `parent_order_id`
- `is_retry_child`
- `conditional_order`
- `trigger_price`
- `conditional_triggered`
- `market_closed_offer` / `deferred_market_open` (weekend / market-closed defer)

Runtime logic lives in `apps/backend-python/app/services/manual_order_runtime.py` and is invoked from `market_data_stream` on live ticks and after broker reconciliation.

Orders linked via `scheduled_trade_id` are strategy-owned and skipped by manual retry/ATM; their lifecycle is owned by Scheduled Break Trade (`docs/skills/scheduled-break-trade.md`).

### Market-closed deferred pending

- If broker placement fails **only** with market closed (`retcode=10018` / `is_market_closed_error`), the API keeps the row as `PLACEMENT_PENDING` with `manual_context.market_closed_offer=true` and returns `market_closed: true` on that result (not `FAILED`).
- Web Place Order shows a modal: save as pending (**OK**) or decline (**No Thanks**).
- **OK** → `POST /orders/{id}/defer-market-open` → status `DEFERRED_MARKET_OPEN`, `place_after` = next Monday **04:30 Asia/Kolkata** (stored UTC). Not sent to the broker yet.
- **No Thanks** → `POST /orders/{id}/decline-defer` → `FAILED`.
- After `place_after`, `deferred_market_open.process_due_deferred_orders` (primary live tick path) places via `place_pending_order_with_limit_fallback`. Still market-closed → leave deferred and retry; other errors → `FAILED`.
- Orders tab **Pending Orders** section lists `DEFERRED_MARKET_OPEN` only when any exist. Local modify/cancel allowed until broker placement; risk↔quantity are bidirectional on modify.

### Conditional SL order

- Manual Place Order → `order_type=SL` only.
- When `conditional_order=true`, the API stores the order as `WAITING_TRIGGER` and does **not** place a broker stop yet.
- Validation:
  - SELL: `trigger_price` must be above current mid; SL `entry` must be below `trigger_price`.
  - BUY: `trigger_price` must be below current mid; SL `entry` must be above `trigger_price`.
- On each live tick (not candle close), once price crosses the trigger (SELL: ask/mid ≥ trigger; BUY: bid/mid ≤ trigger), runtime places the normal broker SL via `place_pending_order_with_limit_fallback`.
- Waiting orders appear in Stop Orders and can be cancelled before the trigger fires.

### Retryable LIMIT / SL order

- Applies to original `LIMIT` and `SL` orders with `retryable_order=true`.
- After one clean stop-loss hit on a filled position, the backend places one child `SL` order with the same entry, stop loss, quantity, target, and trade-management flag.
- If that `SL` is rejected as Invalid price (`retcode=10015`), the backend automatically places a `LIMIT` at the same prices and records `ORDER_SL_FALLBACK_TO_LIMIT` plus `placement_fallback_reason` on the order.
- The child order has `is_retry_child=true` and cannot retry again.

### Automatic trade management

- When `automatic_trade_management=true` and a manual position is open:
  - Book 50% at 4R.
  - Close remaining quantity at target when target is set.
  - Leave the runner open if no target is defined.
- Strategy-owned orders (`trap_reversal_run_id`, `planner_context`, `dry_run`) are skipped.

### Activity events

Manual runtime events include:

- `MANUAL_POSITION_OPEN`
- `MANUAL_PARTIAL_4R_BOOKED`
- `MANUAL_PARTIAL_4R_FAILED`
- `MANUAL_TARGET_EXIT_SENT`
- `MANUAL_TARGET_EXIT_FAILED`
- `MANUAL_RETRY_TRIGGERED`
- `MANUAL_RETRY_ORDER_PLACED`
- `MANUAL_RETRY_ORDER_FAILED`
- `ORDER_SL_FALLBACK_TO_LIMIT` (SL Invalid price — automatic LIMIT at same entry/SL/target)
- `CONDITIONAL_ORDER_ARMED`
- `CONDITIONAL_TRIGGERED`
- `CONDITIONAL_PLACEMENT_FAILED`
- `CONDITIONAL_ORDER_CANCELLED`

`GET /orders/{order_id}/events` returns related parent/child activity with IST timestamps.

## Modify Pending Order

`POST /orders/{order_id}/modify` accepts `{ entry, stop_loss, target?, quantity }` for orders in `PENDING` or `PLACEMENT_PENDING` only.

Broker behavior:

- **Quantity unchanged** — update entry, stop loss, and target at the broker via `modify_pending_order` (`TRADE_ACTION_MODIFY`).
- **Quantity changed** — cancel the existing broker pending order, update the local record, then place a new pending order with the new quantity.
- **No broker order yet** (`meta_order_id` missing) — update the local record and call `place_pending_order`.

Events: `ORDER_MODIFIED`, `ORDER_REPLACED`, `ORDER_CANCELLED_FOR_MODIFY`, or `ORDER_UPDATED` depending on path.

Web, Android, and iOS expose an Edit action on pending rows with the same fields and copy explaining quantity vs in-place updates.

## Local MT5 Notes

The local MT5 adapter converts the reference `place_pending_order`, `cancel_order`, `close_position`, and `modify_position` service calls into `MetaTrader5.order_send()` requests. Prices are normalized to the symbol tick grid (`trade_tick_size` / `point` and `digits`) before every broker send to avoid MT5 retcode 10015 (`Invalid price`). Be careful with real accounts: these endpoints can place live trades.
