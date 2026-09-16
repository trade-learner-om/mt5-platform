# Trap Hunter + backend file logging

- Backend logs now go to a rotating file (`logs/backend.log` by default) instead of the console; set `LOG_TO_CONSOLE=true` for dev.
- New env vars: `LOG_FILE`, `LOG_TO_CONSOLE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`, `TRAP_HUNTER_LOG_LEVEL`.
- Trap Hunter live runtime emits structured `app.trap_hunter` events: FSM rolls, M5 bars, broker orders, H4 rolls, run start/stop, API start/stop.
- DEBUG payloads include candle OHLC, pending entry/SL/qty, armed-bar pending-SL skip, and run context (no secrets).
- `Live tick |` market-data lines demoted from INFO to DEBUG to keep log files bounded.
