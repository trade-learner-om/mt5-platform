# Remove ST-EMA, EMA-VWAP, EMA-Wakeup, ST-RSI-DIV, Trap Hunter

## Summary

Clinically removed five strategy modules from backend and frontend. Trap Reversal, manual orders, Candle Detector, and shared platform infrastructure remain.

## Backend

- Deleted all dedicated service modules (`st_ema_*`, `ema_vwap_*`, `ema_wakeup_*`, `st_rsi_div_*`, `trap_hunter_*`), `indicators.py`, related unit tests, and `scripts/verify_trap_hunter_backtest_trade.py`.
- Removed `pandas-ta` from `requirements.txt` (only used by deleted indicators).
- Stripped routes `/st-ema/*`, `/ema-vwap/*`, `/ema-wakeup/*`, `/st-rsi-div/*`, `/trap-hunter/*` from `main.py`, plus schemas, startup restore, UI settings helpers, candle loaders, and market-data tick wiring.
- Dropped Mongo index setup for `st_ema_runs`, `ema_vwap_runs`, `st_rsi_div_runs`, `trap_hunter_runs`, `trap_hunter_trades` (kept `strategy_results`).
- Removed Trap Hunter log level / logger helpers from `config.py` and `logging_config.py`.

## Frontend

- Deleted dashboards and component folders for the five strategies, plus orphans only used by them (`FeedBrokerConsentModal`, `BacktestResultsPagination`, `backtestCursorPagination`, `brokerTime`).
- Cleaned `App.jsx` nav items, page-usage order, and render branches.

## Docs

- Updated `docs/context/project-context.md` and `docs/skills/automation.md` to document Trap Reversal only for active strategy runtimes.

## Mongo operational cleanup (run on local DB if present)

```js
db.st_ema_runs.drop()
db.ema_vwap_runs.drop()
db.st_rsi_div_runs.drop()
db.trap_hunter_runs.drop()
db.trap_hunter_trades.drop()
db.strategy_results.deleteMany({
  strategy_type: { $in: ["st_ema", "ema_vwap", "ema_wakeup", "st_rsi_div", "trap_hunter"] }
})
// optional:
// db.users.updateMany({}, { $unset: {
//   "ui_settings.st_ema_backtest": "", "ui_settings.st_ema_live": "",
//   "ui_settings.ema_vwap_backtest": "", "ui_settings.ema_vwap_live": "",
//   "ui_settings.ema_wakeup_backtest": "",
//   "ui_settings.st_rsi_div_backtest": "", "ui_settings.st_rsi_div_live": "",
//   "ui_settings.trap_hunter": ""
// }})
```
