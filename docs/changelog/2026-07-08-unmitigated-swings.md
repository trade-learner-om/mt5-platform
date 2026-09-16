# 2026-07-08 - Unmitigated Swings

## Added

- Added `POST /analysis/unmitigated-swings` for international MT5 accounts.
- Added a standalone **Unmitigated Swings** page to the React app and wired it into the main navigation.

## Backend

- Extended `apps/backend-python/app/services/analytics/market_structure.py` with `calculate_unmitigated_levels(df)`.
- The implementation uses the existing 11-bar fractal masks to mark swing highs and lows, then performs a forward chronological pass with monotonic stacks:
  - swing highs remain on a descending resistance stack until a later candle's `high` breaches them;
  - swing lows remain on an ascending support stack until a later candle's `low` breaches them.
- Levels are removed on the exact breach candle, preserving precise mitigation timing while avoiding a backward rescanning pass.
- The route reuses the shared Mongo-first candle history path, so cached candles are used first and MT5 is only consulted on cache miss or gap fill.

## Frontend

- Added `apps/frontend-react/src/pages/UnmitigatedSwingsPage.jsx`.
- The page provides:
  - instrument input;
  - timeframe selector (`1h`, `4h`, `d`);
  - explicit `Analyze` action;
  - table columns for origin time, direction, price, and distance to live price.
- Distance-to-live-price is recomputed from the existing `/ws/live` price stream on every tick without re-triggering backend analysis.
- Header navigation personalization now reads the two primary desktop tabs from backend-backed user settings returned by `/auth/me` instead of a fixed pair or `localStorage`.
- The Unmitigated Swings table now sorts active levels from highest price to lowest price, tints long rows green and short rows red, and resolves live-price subscriptions through the account's broker symbol aliases so the live price renders on brokers that do not stream the canonical symbol name directly.

## UX

- This feature replaces the need to draw long-lived horizontal levels for unmitigated swings by surfacing the exact active levels in a precise, live-updating tabular readout.
- Updated the desktop header navigation to keep only the two primary tabs visible and move the remaining pages into a `>>` overflow menu, reducing header crowding without changing the mobile navigation menu.
- The two visible desktop tabs are now recalculated from each user's most-used pages and persisted under `ui_settings.page_usage` in the user document through `POST /auth/ui-settings`.
