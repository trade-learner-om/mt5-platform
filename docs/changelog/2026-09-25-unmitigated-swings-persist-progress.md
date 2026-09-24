# 2026-09-25 - Persist unmitigated swing automation progress

## Changed

- Each Execute Automation run writes `structure_swing_sessions` with per-level `trade_status`, entry/SL/TP, order ids, and errors.
- Schedule lifecycle updates (`ARMED`, `ORDER_PLACED`, fills/exits, errors) mirror onto the session level document in Mongo.
- `GET /structure/unmitigated-swings/active` and `/sessions` restore progress after refresh; UI loads the active session on page open.
