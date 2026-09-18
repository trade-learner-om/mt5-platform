# Mac Runtime Migration Plan

## Current Context

This platform is currently a local Windows MT5 application:

- `apps/frontend-react` is a Vite React app and can run on macOS without meaningful code changes.
- `apps/backend-python` is a FastAPI app and mostly can run on macOS.
- MongoDB can run locally on macOS.
- The international broker integration is the blocker. It uses the Python `MetaTrader5` package in `apps/backend-python/app/services/metaapi_client.py`, which talks to a local Windows MetaTrader 5 terminal through desktop IPC.

The current local MT5 integration assumes:

- A Windows machine.
- Installed MetaTrader 5 terminal.
- `terminal64.exe` paths for each MT5 account.
- The Python `MetaTrader5` package can initialize the terminal and call `account_info`, `symbol_info_tick`, `orders_get`, `positions_get`, and `order_send`.

That IPC model is not portable to native macOS. Running the existing backend unchanged on a Mac will fail at the MT5 integration layer.

## Short Answer

To run the full product on a Mac, one of these architecture changes is required:

1. Recommended: run the UI and most backend services on macOS, but move MT5 terminal access into a Windows broker bridge service.
2. Simpler: run the whole backend on a Windows machine or Windows VM, and access it from the Mac browser.
3. Experimental: run MT5 under Wine/CrossOver on macOS and try to use the Python `MetaTrader5` package from a compatible Windows Python runtime. This is fragile and not recommended for production.
4. Product-level alternative: replace local MT5 with a broker/cloud API, such as restoring MetaApi.cloud or using a broker-native API.

## Recommended Architecture

Use macOS for the product shell and Windows only for broker execution.

```text
Mac
  React UI
  FastAPI backend
  MongoDB
  Non-MT5 workflows
      |
      | HTTPS or LAN HTTP/WebSocket
      v
Windows MT5 Bridge
  FastAPI or lightweight Python service
  MetaTrader 5 terminal(s)
  Python MetaTrader5 package
```

The Mac backend keeps all product routes and persistent state. The Windows bridge becomes a narrow adapter that exposes only MT5 operations.

## Why a Bridge Is Better

- Keeps the main app portable.
- Preserves the existing local MT5 behavior.
- Avoids trying to make Windows-only MT5 IPC work natively on macOS.
- Keeps all sensitive account credentials encrypted in the main app or explicitly scoped to the bridge.
- Allows multiple MT5 terminal copies to remain on Windows, where `terminal64.exe` and the Python `MetaTrader5` package are supported.

## Required Code Changes

### 1. Introduce a Broker Adapter Boundary

Create a real interface around the current `MetaApiService` behavior.

Current file:

- `apps/backend-python/app/services/metaapi_client.py`

Recommended split:

- `apps/backend-python/app/services/broker/base.py`
- `apps/backend-python/app/services/broker/local_mt5.py`
- `apps/backend-python/app/services/broker/remote_mt5_bridge.py`
- `apps/backend-python/app/services/metaapi_client.py` remains as a compatibility export.

The interface should cover the methods already used by the app:

- `get_account_connection_state`
- `get_account_information`
- `get_account_profile`
- `get_account_profile_with_equity`
- `get_symbols`
- `get_symbol_price`
- `get_symbol_specification`
- `get_risk_context`
- `get_historical_candles`
- `connect_streaming_account` or equivalent live price streaming
- `place_pending_order`
- `cancel_order`
- `close_position`
- `modify_position`
- `get_terminal_state`

The rest of the backend should continue to call `metaapi_service`, but `metaapi_service` should delegate to the configured broker adapter.

### 2. Add Runtime Configuration

Add settings to `apps/backend-python/app/config.py`:

```env
BROKER_ADAPTER=local_mt5
MT5_BRIDGE_BASE_URL=http://windows-host:8010
MT5_BRIDGE_API_KEY=...
```

Adapter modes:

- `local_mt5`: current Windows behavior.
- `remote_mt5_bridge`: macOS-compatible mode that calls the bridge.
- Optional future mode: `metaapi_cloud`.

### 3. Create the Windows MT5 Bridge

Add a small Windows-only service, for example:

```text
apps/mt5-bridge-python/
  app/main.py
  app/mt5_adapter.py
  app/schemas.py
  requirements.txt
  README.md
```

Bridge endpoints should be deliberately narrow:

- `GET /health`
- `POST /accounts/validate`
- `POST /accounts/{account_id}/info`
- `POST /accounts/{account_id}/symbols`
- `POST /accounts/{account_id}/symbols/{symbol}/price`
- `POST /accounts/{account_id}/symbols/{symbol}/specification`
- `POST /accounts/{account_id}/symbols/{symbol}/risk-context`
- `POST /accounts/{account_id}/candles`
- `POST /accounts/{account_id}/orders`
- `POST /accounts/{account_id}/orders/{order_id}/cancel`
- `POST /accounts/{account_id}/positions/{position_id}/close`
- `POST /accounts/{account_id}/positions/{position_id}/modify`
- `POST /accounts/{account_id}/terminal-state`
- `WS /accounts/{account_id}/stream`

Each bridge request should include:

- MT5 login.
- MT5 server.
- Terminal path.
- Encrypted or bridge-local credential reference.
- Symbol/order payload.

Avoid returning MT5 passwords to the frontend or logs.

### 4. Decide Credential Ownership

There are two valid designs.

Option A: main backend owns encrypted credentials.

- Mac backend stores encrypted MT5 password in MongoDB.
- Mac backend decrypts credentials server-side and sends them to the Windows bridge over HTTPS.
- Requires bridge transport security and API-key authentication.

Option B: bridge owns MT5 credentials.

- Mac backend stores only an account reference and terminal path/bridge account id.
- Windows bridge stores encrypted MT5 credentials locally.
- Better isolation, but requires a bridge credential management UI/API.

Recommended first step: Option A for lower migration complexity, with HTTPS and a shared bridge API key.

### 5. Replace Direct Terminal Path UX on Mac

The current account-add workflow asks for a local Windows `terminal64.exe` path. On macOS this should become bridge-aware.

Frontend changes:

- In `ManageAccountModal`, show MT5 terminal path only when `BROKER_ADAPTER=local_mt5`.
- In bridge mode, show:
  - Bridge URL or bridge status.
  - Terminal path on the Windows host.
  - MT5 login/password/server.
  - A “Test Bridge Connection” action.

Backend changes:

- Account creation still writes to `meta_accounts`.
- `credentials.path` becomes the Windows bridge terminal path, not a Mac path.
- Validation calls `remote_mt5_bridge.validate_account`.

### 6. Streaming and Reconciliation

Current live state depends on:

- `market_data_stream`
- `state_manager`
- `trade_planner_runtime`
- `orders` reconciliation

In bridge mode, the Mac backend should not poll the local `MetaTrader5` package. It should either:

- Subscribe to a bridge websocket per account/symbol.
- Or poll bridge REST endpoints at the current cadence.

Recommended:

- Use bridge websocket for ticks.
- Use bridge REST for terminal-state reconciliation.
- Keep `market_data_stream.py` responsible for app-level routing and snapshots.
- Move only raw MT5 communication into the bridge adapter.

### 7. Scripts and Local Operations

Current operational scripts are Windows batch oriented.

Add macOS scripts:

```text
scripts/mt5-platform.sh
scripts/start-frontend.sh
scripts/start-backend.sh
scripts/stop-backend.sh
scripts/status.sh
```

Mac setup should install:

- Python 3.12+
- Node.js
- MongoDB Community Edition or a local MongoDB service
- Backend virtual environment
- Frontend dependencies

Do not install `MetaTrader5` on native macOS backend mode unless using an experimental Windows Python/Wine approach.

### 8. Dependency Changes

Backend dependencies should become conditional:

- Core FastAPI backend dependencies should install on macOS.
- `MetaTrader5` should be installed only for the Windows bridge or `local_mt5` mode.

Recommended structure:

```text
requirements.txt          # portable backend dependencies
requirements-mt5.txt      # Windows-only MetaTrader5 dependency
apps/mt5-bridge-python/requirements.txt
```

### 9. Documentation Updates

Update:

- `docs/context/project-context.md`
- `docs/skills/mt5-integration.md`
- `docs/architecture/local-runtime.md`
- `docs/skills/local-operations.md`

Add:

- `docs/architecture/mac-runtime-plan.md`
- `apps/mt5-bridge-python/README.md`

## Migration Phases

### Phase 1: Make Backend Importable on macOS

Goal: the FastAPI app starts on macOS without importing `MetaTrader5`.

Tasks:

- Move direct `MetaTrader5` imports behind `local_mt5.py`.
- Make `metaapi_client.py` select adapter by setting.
- Ensure non-MT5 routes import cleanly on macOS.
- Add a clear startup error only when `BROKER_ADAPTER=local_mt5` on macOS.

Validation:

- `python -m app.main` or `uvicorn app.main:app` starts on macOS.
- Auth, admin, market selection, frontend, and Mongo routes work.
- MT5 routes return a clear bridge-not-configured error if no bridge is configured.

### Phase 2: Build Remote MT5 Bridge Adapter

Goal: Mac backend can call a Windows bridge for MT5 operations.

Tasks:

- Implement `RemoteMT5BridgeAdapter`.
- Add bridge authentication headers.
- Map bridge responses to the existing `MetaApiService` contract.
- Add timeout and redacted logging.
- Keep existing route contracts unchanged.

Validation:

- Add account from Mac UI.
- Fetch account profile/equity.
- Fetch symbols.
- Fetch price/specification/risk context.

### Phase 3: Bridge Live Prices and Orders

Goal: live prices, risk preview, order placement, and reconciliation work from Mac.

Tasks:

- Implement bridge live tick stream or polling.
- Wire `market_data_stream` to bridge adapter.
- Place, cancel, close, and modify orders through bridge.
- Reconcile pending orders and positions from bridge terminal state.
- Re-test price alerts, manual orders, and trade planner.

Validation:

- Watchlist prices update.
- Price alerts trigger.
- Manual pending orders remain pending when broker shows pending.
- Market orders place correctly.
- Stop loss risk does not exceed configured risk.
- Trade Planner preview and execution remain correct.

### Phase 4: Packaging and Operations

Goal: repeatable local Mac + Windows bridge startup.

Tasks:

- Add `.env.example.mac`.
- Add `.env.example.bridge`.
- Add shell scripts for macOS.
- Add Windows bridge startup script.
- Document firewall and LAN setup.
- Add health checks from Mac backend to bridge.

Validation:

- Fresh Mac setup works from documented steps.
- Fresh Windows bridge setup works from documented steps.
- Health page reports bridge status.

## Operational Topologies

### Topology A: Mac UI + Mac Backend + Windows Bridge

Best for daily Mac use.

```text
Mac browser -> Mac Vite UI -> Mac FastAPI -> Windows MT5 Bridge -> MT5 terminal
```

Pros:

- Mac feels native.
- Most app code runs locally on Mac.
- MT5 remains on supported Windows runtime.

Cons:

- Requires a Windows machine/VM running beside the Mac.
- Requires secure LAN connectivity.

### Topology B: Mac Browser + Windows Backend

Fastest to set up.

```text
Mac browser -> Windows FastAPI/Vite or Windows backend API -> MT5 terminal
```

Pros:

- Minimal code changes.
- Current Windows behavior remains intact.

Cons:

- Backend is not really running on Mac.
- Mac is only a browser/client.

### Topology C: Mac Native Only

Not recommended with the current local MT5 design.

To make this production-grade, the MT5 dependency must be replaced by:

- MetaApi.cloud.
- Broker-native API.
- FIX/API gateway.
- A supported cloud execution service.

## Security Requirements

If using a Windows bridge:

- Use HTTPS or a private trusted network.
- Require a bridge API key or signed token.
- Redact passwords and tokens from logs.
- Do not expose the bridge publicly.
- Bind bridge to LAN/VPN interface only.
- Store bridge API key in `.env`.
- Consider IP allow-listing.

## Testing Checklist

Before calling the Mac runtime production-ready:

- Login/register works on Mac.
- MongoDB persistence works.
- Account add validates through bridge.
- Account switching works.
- Watchlist live prices update.
- Price alerts trigger sound and popup.
- Active alerts move inactive after trigger.
- Manual market order places.
- Manual limit/SL order stays pending locally if broker shows pending.
- Cancel pending order syncs both locally and broker-side.
- Position close works.
- Order reconciliation does not falsely cancel orders.
- Risk preview quantity uses bridge-provided tick value and broker volume step.
- Trade Planner preview works.
- Trade Planner auto-execution works.
- Trap Reversal / Master Break / Scheduled Break Trade live modes work.
- H1 analysis candles load.
- Logs redact secrets.
- Bridge disconnect shows clear UI/API error.

## Suggested Implementation Prompt

Use this prompt for the implementation agent:

```text
We need to make the MT5-platform project run from macOS while preserving local MT5 execution through a Windows bridge.

Current project context:
- Monorepo path: <repo-root>
- Frontend: apps/frontend-react, Vite React.
- Backend: apps/backend-python, FastAPI.
- Database: local MongoDB database mt5_platform.
- Current MT5 integration: apps/backend-python/app/services/metaapi_client.py.
- Current adapter is named MetaApiService/metaapi_service for compatibility, but it uses the local Python MetaTrader5 package and a Windows terminal64.exe path.
- The Python MetaTrader5 package and terminal IPC are Windows-native. The backend cannot run unchanged on native macOS.
- Existing app routes and UI contracts should be preserved.
- Existing workflows include auth, account management, watchlist, /ws/live, manual orders, order reconciliation, price alerts, trade planner, automation, and H1 analysis.

Goal:
Refactor the broker integration so the main FastAPI backend can run on macOS using BROKER_ADAPTER=remote_mt5_bridge, while Windows still supports BROKER_ADAPTER=local_mt5.

Required architecture:
1. Extract the current local MT5 logic into apps/backend-python/app/services/broker/local_mt5.py.
2. Create a broker interface in apps/backend-python/app/services/broker/base.py.
3. Create apps/backend-python/app/services/broker/remote_mt5_bridge.py that calls a Windows bridge over HTTP/WebSocket.
4. Keep apps/backend-python/app/services/metaapi_client.py as a compatibility facade exporting metaapi_service.
5. Add settings:
   - BROKER_ADAPTER=local_mt5|remote_mt5_bridge
   - MT5_BRIDGE_BASE_URL
   - MT5_BRIDGE_API_KEY
6. Create apps/mt5-bridge-python as a small Windows-only FastAPI service wrapping the Python MetaTrader5 package.
7. The bridge must support account validation, account info, symbols, price, specification, risk context, candles, order placement, cancel, close, modify, terminal state, and live tick streaming.
8. Preserve database collections and route contracts.
9. Do not return or log MT5 passwords.
10. Make backend import/start cleanly on macOS without importing MetaTrader5 unless local_mt5 mode is selected.

Important existing files:
- apps/backend-python/app/main.py
- apps/backend-python/app/services/metaapi_client.py
- apps/backend-python/app/services/market_data_stream.py
- apps/backend-python/app/services/state_manager.py
- apps/backend-python/app/services/risk.py
- apps/backend-python/app/config.py
- apps/frontend-react/src/App.jsx
- apps/frontend-react/src/components/ManageAccountModal.jsx
- scripts/mt5-platform.bat
- docs/context/project-context.md
- docs/skills/mt5-integration.md

Implementation constraints:
- Keep changes scoped.
- Preserve current Windows behavior.
- Add tests or targeted validation where practical.
- Add documentation for macOS setup and Windows bridge setup.
- Do not use Docker for MT5 terminal integration.
- Keep credentials encrypted and logs redacted.

Acceptance criteria:
- On Windows, BROKER_ADAPTER=local_mt5 works like today.
- On macOS, backend starts with BROKER_ADAPTER=remote_mt5_bridge without importing MetaTrader5.
- Mac frontend can add/select MT5 accounts through the bridge.
- Live prices, price alerts, manual orders, pending order reconciliation, trade planner, and automation continue to work through bridge mode.
- Pending orders are not falsely marked cancelled when broker still shows pending.
- Documentation explains setup, security, and troubleshooting.
```

## Recommendation

Do not try to make the current Windows `MetaTrader5` package run natively on macOS. The safest production path is:

1. Keep MT5 terminal execution on Windows.
2. Add a small authenticated Windows bridge.
3. Make the main backend broker-adapter driven.
4. Run the UI/backend/MongoDB on Mac only after the adapter split is complete.
