---
name: mt5-websocket-live-state
description: >-
  /ws/live snapshot model, heartbeat, chartless terminal live updates, and
  market_data_stream fan-out. Use when editing ws_live, state_manager, or
  frontend/mobile websocket clients.
---

# Websocket Live State

Read first: `docs/skills/websocket-live-state.md`.

REST for commands/hydration; websocket for live state. 20s application heartbeat plus client pings.
