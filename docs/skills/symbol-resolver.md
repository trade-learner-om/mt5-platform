# Symbol Resolver

## Purpose

Map canonical instrument requests (`GOLD`, `XAUUSD`, `EURUSD`, …) to each broker’s live symbol name (`XAUUSD+`, `GOLD`, `EURUSDm`, …).

## Implementation

`apps/backend-python/app/services/symbol_resolver.py`  
Helpers: `apps/backend-python/app/services/mt5_symbol_utils.py`

Aliases are stored on `meta_accounts.symbol_aliases`, auto-detected on account connect, and editable in Manage Accounts (`GET`/`PATCH` account symbol-alias routes in `main.py`).

## Rules

- Always resolve through the account’s aliases **before** watchlist, live stream, orders, candle history, trade planner, or strategy runtimes talk to MT5.
- Prefer stored alias when present; otherwise match against `symbols_get()` with gold/forex heuristics.
- `build_auto_detect_aliases` / `detect_account_symbol_aliases` refresh aliases from the live terminal symbol list.
- Display may keep the user’s requested name while broker calls use the resolved symbol.

## Key functions

- `resolve_broker_symbol(requested, available_symbols, account=...)`
- `resolve_broker_symbol_for_account(account, requested)`
- `lookup_live_price(live_prices, symbol)` — tolerant key lookup against live price maps
- `is_gold_request` / `default_gold_symbol` — XAU/GOLD family helpers
