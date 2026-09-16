# Trend Pilot: in-position UI, open P/L, duplicate SL fix

## Summary

After a long/short entry fill, Trend Pilot now reliably cancels opposite entry stops, clears redundant position SL, and keeps a single reversal stop at 2× quantity. The active run card shows open position details, live open P/L, and a single status badge.

## Changes

- `_cancel_armed_entry_orders`: broker scan cancels orphan entry stops even when IDs are untracked
- `_enter_position`: always cancels armed orders, clears position SL, dedupes pending stops at SL
- `_detect_armed_fills`: position-first (no pending-stop gate)
- `reconcile_broker_state_from_poll` on `GET /trend-pilot/active` cleans live trades
- Snapshot: `position_entry_price`, `position_stop_loss`, `unrealized_pnl`, `reversal_order_quantity`
- Active run card: single LONG/SHORT badge, open position section, total Run P/L with realized/open breakdown
- P/L values color by sign (red loss, green profit); hide Long/Short entry panels when in position
- Entry stops no longer attach broker SL (prevents 0.02 position SL on fill); dedupe never keeps entry-sized pending at SL; reconcile bugfix
