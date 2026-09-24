# 2026-09-24 - Unmitigated Swings UI + M1 execute automation

## Added

- Sidebar page **Unmitigated Swings** (`unmitigated-swings`): analyze instrument on H4/H1/M15, show N highs/lows, **Execute Automation**.
- API (not the removed `/analysis/*` family):
  - `POST /structure/unmitigated-swings` — active unmitigated highs/lows
  - `POST /structure/unmitigated-swings/execute` — one-shot M1 Scheduled Break Trade per level (`retryable_order=false`)
  - `GET /structure/unmitigated-swings/session/{id}` — Active/Mitigated polling
- Session collection `structure_swing_sessions`. Levels mark **Mitigated** when M1 close breaks them.
- Placement target for swing-sourced schedules: farther of **4R** vs prior structure-TF candle high (BUY) / low (SELL).

## UI

- [`UnmitigatedSwingsPanel.jsx`](apps/frontend-react/src/components/structure/UnmitigatedSwingsPanel.jsx) + nav entry in AppShell/App.
