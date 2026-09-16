# Master Break end-to-end wiring

## Summary

Wired the existing Master Break service modules into FastAPI routes, market-data tick/stream symbol unions, Mongo indexes, and a React Live/Backtest/History dashboard.

## Backend

- Pydantic schemas for settings, start/stop, and backtest inputs
- `/master-break/*` routes (live, settings, backtest CRUD + trades pagination)
- Stream hooks for required symbols + `handle_price` after trap reversal
- `master_break_runs` index on `(user_id, status, updated_at)`
- Startup restore of RUNNING runs before stream restore

## Frontend

- `MasterBreakDashboard` with settings modal
- Shared `backtestCursorPagination` + First/Prev/page-input/Next/Last pager
- App nav item `master-break` with Indian-market blocker

## Docs

- project-context routes + short Master Break paragraph
- automation skill Master Break section
