# Trap Hunter live status UI

- Active run cards show animated status pills per FSM state (IDLE, SWEPT, ARMED, IN_POSITION, DISABLED).
- M5 candle-close countdown in `HH:MM:SS` with "Waiting candle close" label.
- Start button disabled while a run is active for the symbol; header Stop stops selected accounts.
- Backend snapshot includes `running_m5_close_at` and `account_id` for live UI.
- Live settings modal supports multi-account selection, persisted as `account_ids` in Trap Hunter settings.
