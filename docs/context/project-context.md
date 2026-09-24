# Project Context

## Goals

This project is now a local-only MT5 implementation of the reference SignalBridge / Trade Automation workflow from `git/trade-automation-core` and `git/trade-automation-ui`. The UI and backend behavior should match the reference app for authentication, admin users, market/account selection, international and Indian market separation, watchlists, live websocket state, manual orders, notifications, and trade planner workflows, with local strategy runtimes replacing the removed legacy main Automation tab.

The only intended product difference is international broker connectivity. The reference app used MetaApi.cloud for international MT5 accounts; this project replaces that layer with the local Windows MetaTrader 5 terminal through the Python `MetaTrader5` package.

## Architecture

This is a local-first monorepo:

- `apps/backend-python`: FastAPI API adapted from the reference backend, running directly on Windows.
- `apps/frontend-react`: Vite React frontend adapted from the reference UI.
- `apps/android-app`: native Kotlin/Jetpack Compose Android client for LAN access to the existing backend.
- `apps/ios-app`: native SwiftUI iOS client with feature parity to the Android app for LAN access to the existing backend.
- `docs`: AI-readable documentation and changelog.
- `shared`: reserved for future shared assets or generated contracts.

Docker is not used. The backend must run on the same local Windows system where MetaTrader 5 is installed because the Python `MetaTrader5` package talks to a local terminal process.

## Backend Workflow

The backend exposes route contracts including `/auth/*`, `/admin/users`, `/accounts`, `/market/select`, `/watchlist`, `/market-price`, `/risk-preview`, `/orders`, `/trade-planner/*`, `/trap-reversal/*`, `/master-break/*`, `/scheduled-trades/*`, and `/ws/live`. The old `/automation/reversal-5m/*`, `/analysis/market-structure`, `/analysis/unmitigated-swings`, `/gold-strategy/*`, `/continuation-failure/*`, `/st-ema/*`, `/ema-vwap/*`, `/ema-wakeup/*`, `/st-rsi-div/*`, `/trap-hunter/*`, and `/trend-pilot/*` route families have been removed.

Application authentication uses bcrypt password hashes and JWT access tokens with a session id. International account creation accepts local MT5 login, password, and server, validates connectivity through `MetaTrader5.initialize(login=..., password=..., server=...)`, and stores an encrypted credential payload in `meta_accounts.api_token`.

MT5 operations are blocking desktop-terminal IPC calls, so the compatibility adapter serializes local terminal access and runs operations off the event loop. Account creation requires a terminal path detected on the machine where the backend and MT5 terminal are running, then validates that the connected terminal login/server match the account being added.

Live market processing also avoids blocking the main FastAPI event loop. Authentication lookup, health-check database ping, and Indian-market stream work can still be offloaded to background threads, while international live-stream restore/refresh/reconcile/tick-ingest and websocket heartbeat hop onto `market_data_stream`'s dedicated tick loop. Request-path and live-snapshot MongoDB access use awaited Motor calls. The MT5 adapter uses a per-account session manager to serialize terminal access, and the streaming connection pool uses a thread lock for shared connection dicts.

The trap-reversal runtime is built around a thread-safe singleton manager plus a per-symbol `DoubleTrapFSM`. H1 structural supports and resistances are indexed once at startup using fractal swing detection in `app.services.analytics.market_structure`, then filtered by a forward chronological mitigation pass so the live engine starts only with still-active levels. Live ticks are routed by symbol in `O(1)` and each FSM processes scalar prices and a tiny rolling M1 candle buffer instead of pandas dataframes.

Master Break is a separate international XAUUSD/GOLD strategy: dual-side FSMs watch a master timeframe (H4/H6/H12/D1) for break levels, arm pending entries on an execution timeframe (M1/M5/M15), then manage multi-target partials and breakeven. Live routing shares the market-data tick path with trap reversal; settings and backtest results live under `/master-break/*` and `strategy_results` with `strategy_type=master_break`.

Scheduled Break Trade is a user-level break tool (not Master Break): create a schedule with a price level and M1/M5/M15 timeframe on the selected international account, wait for a completed candle close past the level, arm on the next valid red/green candle, place SL (LIMIT fallback on Invalid price for the primary leg only), and optionally re-place the same SL once after stop-out under `RETRY_*` statuses on the same document. UI is a root sidebar page (**Scheduled Trade**, page id `scheduled-trade`); API under `/scheduled-trades/*`.

## Data Storage

MongoDB runs locally at `mongodb://localhost:27017` with database `mt5_platform`. The backend database layer now uses Motor (`AsyncIOMotorClient`) behind a repository-local compatibility wrapper in `apps/backend-python/app/db.py` so existing collection-style code can continue working while Mongo operations move onto the async runtime.

Important collections follow the reference app:

- `users`: application user identity, bcrypt hash, session state, selected market, selected accounts, admin flags.
- `meta_accounts`: both international local-MT5 accounts and Indian/Mstock accounts. International account credentials are encrypted.
- `watchlist_items` and `indian_watchlist_items`.
- `orders`, `order_events`, and `notifications`.
- `scheduled_trades` and `scheduled_trade_events` for Scheduled Break Trade lifecycles.
- `trade_plans`.
- `candles`, `h1_candles`, `m1_candles`, and `analysis_candles`.
Application passwords are never recoverable. MT5 passwords are encrypted at rest and are never returned through the API.

## Frontend Workflow

The frontend is the reference SignalBridge UI ported into `apps/frontend-react`. It uses REST for explicit actions and `/ws/live` for live state. Account and market switches should refresh silently. Indian and international workflows must remain separate.

The Android client in `apps/android-app` is native Compose, not a WebView. The current build connects directly to the deployed backend at `https://api.signalbridge.in` and `wss://api.signalbridge.in/ws/live`, authenticates against that API, and loads dashboard/watchlist/planner bootstrap data in parallel. The Trading tab sends `retryable_order` and `automatic_trade_management` on order placement; Positions rows can expand into `GET /orders/{id}/events` activity timelines. The mobile UI uses bottom navigation, compact cards, and modal sheets for new orders instead of always-visible forms; Watchlist trade actions prefill the order sheet symbol.

The iOS client in `apps/ios-app` mirrors the Android app: SwiftUI native UI, saved JWT storage, Face ID or passcode unlock, the same bottom tabs and modal order sheets, direct `https://api.signalbridge.in` / `wss://api.signalbridge.in/ws/live` connectivity, and local notifications for order and strategy status changes.

Account deletion follows the reference safety checks for active orders and trade planner plans. After the database delete and selected-account recalculation, live stream refresh is best-effort so a local MT5 IPC or market stream problem cannot make a successful account deletion appear failed.

Trade Planner plans default to execution-enabled when created. Turning execution off, deactivating a plan, or deleting a plan must first cancel any linked pending broker orders stored with `planner_context.plan_id`; filled/open positions are not force-closed by plan deletion or deactivation.

The Place Order ticket includes a Candle Detector helper for international MT5 accounts. It calls `/orders/candle-detector/preview`, scans the last five completed broker candles for Hammer or Shooting Star patterns, then populates the normal ticket as an `SL` order. Hammer maps to `BUY` with entry at candle high plus one point and suggested stop loss at candle low minus one point. Shooting Star maps to `SELL` with entry at candle low minus one point and suggested stop loss at candle high plus one point. Stop loss stays editable, and final sizing/placement still flows through `/risk-preview/multi` and `/orders`.

The Trading tab order ticket also supports manual trade options stored on each `orders` document in `manual_context`. `Retryable order` applies to `LIMIT` and `SL` orders (default on). After one clean stop-loss hit on a filled trade, the backend re-places the setup once as an `SL` order with the same entry, stop loss, quantity, and target (with LIMIT fallback on Invalid price). `Automatic trade management` is available for all order types (default on). When enabled, the manual order runtime books 50% at 4R, closes the remaining quantity at target when a target is set, and leaves the runner open if no target is defined. Conditional SL (`conditional_order` + `trigger_price`) arms as `WAITING_TRIGGER` until a live tick crosses the trigger. Runtime code lives in `apps/backend-python/app/services/manual_order_runtime.py`. All lifecycle actions are persisted in `order_events` with IST timestamps and are exposed through `GET /orders/{order_id}/events` and the Positions order activity panel.

The web frontend is now a chartless execution and data terminal. Historical candle infrastructure still exists on the backend (`GET /chart/candles` plus the MongoDB candle caches) for broker-side analytics and support tooling, but the React UI no longer renders TradingView/Lightweight Charts or exposes chart timeframe selectors. The primary web shell is a Bloomberg-style terminal layout: collapsible sidebar, top server/equity bar, and a dense three-column dashboard for watchlist, FSM engines, and live positions.

Subscribed international symbols also persist M1 candles in `m1_candles` and mirror them into the broker-scoped `candles` cache. Live ticks are queued and processed sequentially so candle high/low formation does not drop intermediate ticks, and live OHLC uses MT5-style bid candles.

The legacy main Automation tab/runtime and `/automation/reversal-5m/*` routes have been removed. Neutral candle pattern helpers live in `apps/backend-python/app/services/candle_patterns.py` for the order ticket Candle Detector.

The web app includes a standalone **Trap Reversal** command center (international MT5 only) and also embeds that module into the chartless trading terminal. It calls the `/trap-reversal/*` route family, renders H1 support/resistance proof lists, and polls live FSM summaries for active symbols without adding work to the websocket snapshot path. A separate **Master Break** page (`/master-break/*`) covers live start/stop, settings, and gold backtests with cursor-paginated history. Live watchlist cells and position PnL rows animate on websocket price changes with Framer Motion rather than using any chart surface.

International risk sizing must never round volume upward beyond configured risk. Quantity calculation floors to the broker `volumeStep` using live MT5 tick value/volume constraints when available, and rejects orders when the configured risk is below the broker minimum volume risk. For XAU/GOLD, `0.01` is a pippet/broker point and `0.10` is one pip; point buffers use broker point size, while SL pip distance and risk sizing use `0.10`.

International MT5 brokers expose different symbol names for the same instrument (`XAUUSD`, `XAUUSD+`, `GOLD`, `EURUSDm`, etc.). Canonical requests like `GOLD` or `XAUUSD` are resolved per account through `apps/backend-python/app/services/symbol_resolver.py`, using stored `meta_accounts.symbol_aliases` (auto-detected on account connect, editable in Manage Accounts) before watchlist, live stream, orders, charts, trade planner, and strategy runtimes talk to MT5.

## Diagnostics

Backend validation and MT5 adapter logs must redact passwords, encrypted credentials, and tokens. Logs may include masked account ids, MT5 server names, route names, and validation details.

## Local Operations

Use `scripts/mt5-platform.bat` to manage both local servers. The command supports `start`, `stop`, `restart`, and `status`, and is intended to be available on the user's PATH as `mt5-platform`. During startup it can create local `.env` files, install dependencies, and generate development JWT/Fernet secrets when placeholders are still present.

## Documentation maintenance

- Index and skill map: `docs/README.md`.
- Read `docs/context/project-context.md` plus matching `docs/skills/*.md` before coding (`AGENTS.md`).
- Update changelog under `docs/changelog/` after significant behavior changes.
- Cursor wrappers live in `.cursor/skills/`; keep them thin and point at `docs/skills`.

## Active strategy runtimes

- Trap Reversal — `docs/skills/trap-reversal.md`
- Master Break — `docs/skills/master-break.md`
- Scheduled Break Trade — `docs/skills/scheduled-break-trade.md`

## Contributor Preferences

- AI agents should commit and push completed work to `origin` by default; do not leave changes only on disk unless the user asks to hold the push.

## Design Decisions

- Use native Windows backend execution for real MT5 integration.
- Preserve the reference app workflow and route contracts where practical.
- Replace MetaApi.cloud only for international account/trading operations.
- Keep Indian/Mstock behavior separate from international MT5 behavior.
- Encrypt recoverable MT5 credentials with Fernet-derived secret storage instead of hashing them.
- Keep MT5 server plaintext in metadata where useful, but never expose MT5 passwords.
- Keep the documentation system updated with every significant change.
