# Chart Datafeed

## Purpose

Provide candle history from local MT5 for backend analytics, support tooling, and any future consumers now that the React frontend no longer renders a chart.

## Backend

Chart candles are served by `GET /chart/candles` in `apps/backend-python/app/main.py`.

Required query parameters:

- `account_id`: MongoDB id of a user-owned international MT5 account.
- `symbol`: logical symbol such as `GOLD`, `XAUUSD`, or `EURUSD`. The backend resolves this to the broker-native symbol for the selected account before fetching candles.
- `timeframe`: one of `1m`, `5m`, `15m`, `45m`, `1h`, `4h`, `d`.
- `from` and `to`: Unix seconds or ISO timestamps.
- `limit`: capped at 5000.

The endpoint delegates to `apps/backend-python/app/services/candle_history.py`. It checks MongoDB first, fetches missing candles from local MT5 through `metaapi_service.get_historical_candles()`, upserts the fetched rows, and returns sorted bars for the chart. Recent chart ranges are refreshed from MT5 before returning so broker candles override partial live-built cache rows.

Live M1 candle formation is handled by `apps/backend-python/app/services/m1_candle_builder.py`. The stream manager queues every received tick per session and processes ticks sequentially, so live high/low formation does not drop intermediate ticks. Live OHLC values use the MT5 chart convention of bid-based candles, falling back to `price` or `ask` only if bid is unavailable.

## Unmitigated swing levels

`unmitigated_levels_for_candles` / `get_unmitigated_levels_for_symbol` in `candle_history.py` convert Mongo/MT5 candle lists into active swing highs and lows via `app.services.analytics.market_structure`. Trap Reversal H1 indexing uses the same detector. Do not restore the removed `/analysis/unmitigated-swings` or `/analysis/market-structure` routes.

## MongoDB Scope

Chart candles are stored in `candles` with broker/account scope:

- `broker`
- `broker_account_id`
- `market`
- `symbol`
- `timeframe`
- `time`

This is required because similarly named symbols and candle feeds can differ by broker/account.

## Frontend

The previous web chart component has been removed as part of the execution-terminal redesign. The candle route and cache remain available for backend-side workflows, but the React UI no longer requests chart history or subscribes symbols with websocket source `chart`.
