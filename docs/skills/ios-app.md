# iOS App

## Purpose

Native SwiftUI client in `apps/ios-app` with feature parity goals vs the Android app for production API access.

## Connectivity

Default build uses fixed production hosts (`AppConfig.swift`):

- REST: `https://api.signalbridge.in`
- WebSocket: `wss://api.signalbridge.in/ws/live`

LAN/debug hosts are optional when `useFixedHost` is false. See `apps/ios-app/README.md` for Xcode, signing, and ATS notes.

## Implementation notes

- Saved JWT, Face ID / passcode unlock, bottom tabs, modal order sheets.
- Live websocket hydration for watchlist, orders, notifications.
- Trap Reversal screens call `/trap-reversal/*` (`StrategyViews.swift`, `AppViewModel.swift`).
- Local notifications for order/strategy status changes.

## Known debt

Android and iOS still contain **stale** calls to removed backends:

- `/gold-strategy/*`
- `/trend-pilot/*`

Do not restore those backend routes. When touching mobile strategy UI, remove or gate dead clients and prefer Trap Reversal / Master Break / Scheduled Break Trade surfaces that match the live API.

## Related

- Android: `docs/skills/android-app.md`
- Product overview: `docs/context/project-context.md` (mobile paragraphs)
