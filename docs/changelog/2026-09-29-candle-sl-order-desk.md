# Candle SL order desk

## Summary

The trading screen ticket is an SL-only desk. M1, M5, and M15 (default M5) load the last completed candle. Buy and Sell then fill entry and stop one tick outside that candle, with SL pips, risk-based quantity, and optional RR. The bottom tracker shows today's orders as Recent and older orders as cursor-paged History, labeled Placed, In Position, or Closed.

## Details

- `POST /orders/quick/preview` returns OHLC before a side is chosen, then candle entry, stop, and `sl_pips`.
- The desk places with `POST /orders` and `order_type: "SL"`.
- Pending quantity edits still cancel and replace. Open positions update stop and target only.
- `GET /orders/history` returns `{ records, next_cursor }` instead of offset pages.
