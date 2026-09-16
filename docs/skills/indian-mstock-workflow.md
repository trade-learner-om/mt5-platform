# Indian Mstock Workflow

## Purpose

Keep the reference app's Indian market workflow separate from the international local-MT5 workflow.

## Implementation

Indian account/session/watchlist/strategy endpoints live in `apps/backend-python/app/main.py`:

- `POST /indian/accounts/{account_db_id}/request-otp`
- `POST /indian/accounts/{account_db_id}/verify-otp`
- `GET /indian/watchlist`
- `GET /indian/instruments/suggest` (`kind=fno_equity` filters F&O cash underlyings)
- `POST /indian/strategy/preview`
- `POST /indian/watchlist`
- `DELETE /indian/watchlist`
- `POST /indian/pe-cycle/backtest` — PE→Stock→CE monthly cycle backtest
- `GET /indian/pe-cycle/backtests`
- `GET /indian/pe-cycle/backtest/{id}`
- `DELETE /indian/pe-cycle/backtest/{id}`

Mstock-specific client code lives in `apps/backend-python/app/services/mstock_client.py` and `apps/backend-python/tradingapi_a`.
PE→Stock→CE backtest engine: `indian_pe_stock_ce_backtest.py`, contracts: `indian_fno_contracts.py`, persistence: `indian_pe_cycle_persistence.py`.

## Rule

Do not mix Indian/Mstock accounts into international local-MT5 selectors, streams, or order workflows unless the reference app already does so explicitly.
