# Trend Pilot strategy runtime

## Added

- Isolated **Trend Pilot** automation for XAUUSD on international MT5 accounts.
- `apps/backend-python/app/services/trend_pilot_runtime.py` with `TrendPilotFSM` + `TrendPilotManager` (separate `active_runs` memory from trap-reversal).
- `apps/backend-python/app/services/trend_pilot_persistence.py` for `trend_pilot_runs` and `order_events` rows tagged with `strategy_type: "trend_pilot"`.
- REST routes: `POST /trend-pilot/start`, `POST /trend-pilot/stop`, `GET /trend-pilot/active`, `GET /trend-pilot/runs`, `GET /trend-pilot/history/{run_id}`.
- H4 two-candle window logic with BUY/SELL STOP arming, opposite-edge SL, and immediate reversal rolls persisted as `TREND_PILOT_ROLL` events.
- Independent `market_data_stream` consumer wrapped in isolated `try/except`.
- Trend Pilot live and backtest sizing now use user-provided **quantity** (default `0.01` lots) instead of account risk amount.

## Isolation

- No changes to `trap_reversal_automation.py` or `manual_order_runtime.py`.
- Trend Pilot orders omit `manual_context.automatic_trade_management` to avoid manual runtime interference.

## Tests

- `apps/backend-python/test_trend_pilot_runtime.py`
