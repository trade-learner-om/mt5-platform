---
name: mt5-mobile-clients
description: >-
  Native Android (Compose) and iOS (SwiftUI) clients for the production API.
  Use when editing apps/android-app or apps/ios-app, mobile order sheets,
  websocket clients, or strategy screens.
---

# Mobile Clients

Read first:

1. `docs/skills/android-app.md`
2. `docs/skills/ios-app.md`
3. `apps/ios-app/README.md` (Xcode / ATS)

Production hosts: `https://api.signalbridge.in` and `wss://api.signalbridge.in/ws/live`.

Known debt: stale `/gold-strategy/*` and `/trend-pilot/*` callers — remove them; do not restore backend routes.
