---
name: mt5-integration
description: >-
  Local Windows MetaTrader 5 adapter, terminal paths, account validation, tick
  polling, and EA tick bridge. Use when working on metaapi_client, MT5 connect,
  terminal detection, /ws/mt5/ticks, or international account creation.
---

# MT5 Integration

Read first:

1. `docs/skills/mt5-integration.md`
2. `docs/skills/mt5-ea-tick-bridge.md`
3. `docs/skills/security-credentials.md` (credential handling)

Key code: `apps/backend-python/app/services/metaapi_client.py`, `apps/backend-python/app/mt5/terminal_detection.py`.

One unique `terminal64.exe` path per MT5 account. Always `shutdown()` after connection attempts. Never log or return MT5 passwords.
