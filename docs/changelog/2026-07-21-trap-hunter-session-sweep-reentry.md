# Trap Hunter session sweep re-entry rules

## Summary

Aligns same-direction re-entry within an H4 session with live trading rules:

- After a trade is taken from an H4 sweep, that sweep level is consumed for the session.
- A second setup in the same H4 requires a **new session extreme** (lower low for longs, higher high for shorts), then a sweep of that level.
- After a stop loss (pending or initial), the strategy waits for a **re-sweep of the SL level** before arming again — not an immediate re-arm on the old H4 anchor alone.

## Technical

- `TrapHunterSideEngine` tracks `session_extreme`, `active_sweep_level`, `last_used_sweep_level`, and `need_fresh_extreme`.
- Sweep detection uses the resolved active level instead of a static H4 anchor for the whole session.
- Persistence and backtest audit updated for session-sweep rolls.
