# Indian Mstock Workflow

## Purpose

Keep the reference app's Indian market workflow separate from the international local-MT5 workflow.

## Implementation

Indian account/session/watchlist endpoints live in `apps/backend-python/app/main.py`:

- `POST /indian/accounts/{account_db_id}/request-otp`
- `POST /indian/accounts/{account_db_id}/verify-otp`
- `GET /indian/watchlist`
- `GET /indian/instruments/suggest` (`kind=fno_equity` filters F&O cash underlyings)
- `POST /indian/watchlist`
- `DELETE /indian/watchlist`

Mstock-specific client code lives in `apps/backend-python/app/services/mstock_client.py` and `apps/backend-python/tradingapi_a`.
Indian strategy preview and PE→Stock→CE backtest routes have been removed. Keep the Indian watchlist.

## Rule

Do not mix Indian/Mstock accounts into international local-MT5 selectors, streams, or order workflows unless the reference app already does so explicitly.
