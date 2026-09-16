# Trend Pilot backtest history pagination

## Summary

Added cursor-based pagination to `GET /trend-pilot/backtests` so list responses stay small and fast.

## API

- Query params: `limit` (1–50, default 20), optional opaque `cursor`
- Response envelope: `{ results, page_info }` with `has_next_page`, `end_cursor`, `has_previous_page`
- List queries project out `rolls`; detail endpoint unchanged

## Clients

- Web Trend Pilot dashboard uses `useInfiniteQuery` with a Load more button
- Android and iOS backtest tabs append pages on Load more

### Follow-up

- Web backtest list disables live polling, normalizes `page_info`, auto-loads on scroll, and keeps Load more visible outside the scroll area
- Web backtest list requests 5 results per page so Load more appears with smaller histories
- Web backtest list uses numbered pages (`page` + `limit`) with Prev/Next, page numbers, and per-page input; mobile keeps cursor load-more
- Web and iOS backtest lists fetch cursor-based pages only (`limit` + `cursor`) with classic pager UI and `total_count` metadata
- Web Trend Pilot entry roll rows use green/red shaded backgrounds for LONG and SHORT entries
- Backtest list API and clients now include persisted `quantity` on each result; entry roll rows show lot size
- iOS Trend Pilot backtest form is hidden behind a Run backtest button and only expands when starting a new run
- iOS backtest From/To fields use native date pickers instead of plain text input
- iOS Trend Pilot backtest/history P/L uses green/red coloring with bolder type

## Backend

- `list_backtest_results_page` in `trend_pilot_backtest_persistence.py` with base64 JSON cursors on `(created_at, _id)`
- List serialization uses persisted `summary` only (no `rolls` dependency)
