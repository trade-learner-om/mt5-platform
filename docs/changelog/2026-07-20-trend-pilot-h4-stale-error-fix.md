# Trend Pilot: fix misleading H4 stale-feed error

## Summary

When the broker H4 feed matches the stored C2 candle (window already current), Trend Pilot no longer shows a red "roll overdue / stale candle feed" error. It clears `last_error`, reschedules the next H4 close, and waits quietly for the next bar.

## Changes

- `_on_h4_close`: equal `feed_c2 == stored_c2` clears error and sets `running_h4_close_at` to next close; only warns when feed is behind stored C2
- `sync_h4_window_from_broker`: clears `last_error` when broker C1/C2 already match stored window
- Weekend/session H4 gaps log at INFO with "(expected over weekends)" instead of WARNING "backtest H4 gap"
