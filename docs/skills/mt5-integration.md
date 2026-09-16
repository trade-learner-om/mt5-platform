# MT5 Integration

## Purpose

Replace the reference app's MetaApi.cloud international broker layer with a local MetaTrader 5 terminal adapter while keeping the reference service contract intact.

## Implementation

The compatibility integration lives in `apps/backend-python/app/services/metaapi_client.py`. The class and singleton remain named `MetaApiService` and `metaapi_service` because the copied reference backend expects that contract, but the implementation uses the local Python `MetaTrader5` package.

It wraps:

- `MetaTrader5.initialize(login=..., password=..., server=...)`
- `MetaTrader5.account_info()`
- `MetaTrader5.symbols_get()`, `symbol_info()`, and `symbol_info_tick()`
- `MetaTrader5.copy_rates_from()` and `copy_rates_from_pos()`
- `MetaTrader5.order_send()`
- `MetaTrader5.history_deals_get()` for broker-backed trade history
- `MetaTrader5.orders_get()` and `positions_get()`
- `MetaTrader5.shutdown()`

Always call `shutdown()` after each connection attempt so terminal resources are released.

Live prices are polled once per second from subscribed symbols through local MT5 `symbol_info_tick()`. An MT5 Expert Advisor or bridge can also push ticks into backend websocket `WS /ws/mt5/ticks?secret=<account-secret>&account_id=<login-or-account-db-id>`. The account secret is generated per international MT5 account and shown in the web app under Manage Accounts. If an EA/bridge is used, it should send a message on every `OnTick()` event for subscribed symbols:

```json
{ "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002, "time": "2026-06-18T03:30:00Z" }
```

Batch messages are also supported:

```json
{ "ticks": [{ "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002 }] }
```

The backend authenticates the websocket against the per-account saved secret, routes valid ticks into `market_data_stream`, and fans resulting snapshots out through `/ws/live`.

International accounts are stored in `meta_accounts`. `account_id` is the MT5 login. `api_token` stores an encrypted JSON payload containing the MT5 password, server, and terminal path. This preserves the reference database contract while removing MetaApi tokens.

Account creation requires a terminal path, but the intended workflow is to detect it on the machine running the backend and MT5 terminal. For multiple MT5 accounts, each account must use a unique MT5 installation/copy with its own `terminal64.exe` path. Running multiple processes from the same executable path is not enough because the Python `MetaTrader5` IPC API cannot reliably choose between them. If the backend moves to another machine, re-detect and save terminal paths on that machine.

## Dependencies

- Windows local runtime
- Installed MetaTrader 5 terminal
- Python `MetaTrader5` package
- Valid broker server name, account number, and password
- MT5 EA or local bridge process capable of opening a websocket/TCP socket and pushing tick JSON to the backend

## Usage

Use `metaapi_service` methods for international workflows:

- `get_account_profile_with_equity`
- `get_symbol_price`
- `get_symbols`
- `get_symbol_specification`
- `get_historical_candles`
- `place_pending_order`
- `cancel_order`
- `close_position`
- `modify_position`

Do not log MT5 passwords. Do not return decrypted credentials to the frontend.

The backend logs sanitized MT5 diagnostics for failed connection attempts. Logs may include masked login, server, MT5 error code, and MT5 error message, but never the MT5 password.

Run `scripts/mt5-diagnose.bat` to verify whether the backend Python environment can see a running MT5 terminal and whether `MetaTrader5.initialize()` succeeds without credentials.

For LAN/mobile access, allow backend port `8000` through Windows Firewall. The EA/bridge connects to the per-account URL shown in Manage Accounts.
