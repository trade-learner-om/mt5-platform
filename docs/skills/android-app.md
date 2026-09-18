# Android App

## Purpose

Native Kotlin/Jetpack Compose client in `apps/android-app` for the SignalBridge backend (not a WebView wrapper).

## Connectivity

Current production build defaults to:

- REST: `https://api.signalbridge.in`
- WebSocket: `wss://api.signalbridge.in/ws/live`

LAN/host setup UI still exists for non-fixed builds. Prefer documenting the production fixed-host path unless changing `AppConfig`-equivalent Android host logic.

## Implementation

- OkHttp for REST and websocket.
- Bottom navigation, compact cards, modal order sheets.
- Trading sends `retryable_order` and `automatic_trade_management` on place.
- Positions rows expand into `GET /orders/{id}/events` timelines.
- Trap Reversal uses `/trap-reversal/*` (`StrategyScreens.kt` / related).

## Known debt

Same as iOS: leftover `/gold-strategy/*` and `/trend-pilot/*` clients against removed backends. Do not restore those routes — delete or replace mobile callers when working in this area.

## Related

- iOS: `docs/skills/ios-app.md`
- Orders: `docs/skills/trading-order-lifecycle.md`
