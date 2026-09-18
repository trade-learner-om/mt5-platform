# Documentation System

This folder is the AI-readable knowledge base for the MT5 platform. Agents must read context and relevant skills before coding (`AGENTS.md`).

## Layout

| Path | Role |
|------|------|
| `docs/context/project-context.md` | Canonical product and architecture reference |
| `docs/architecture/` | Runtime topology and migration plans |
| `docs/skills/` | Focused implementation skills (read the ones that match the task) |
| `docs/changelog/` | Dated records of significant behavior changes |
| `docs/guides/` | Historical / specialized guides (check status headers) |
| `.cursor/skills/` | Cursor auto-discovery wrappers that point back into these docs |
| `.cursor/rules/` | Persistent agent rules for this repo |

## When to update what

1. **Behavior or architecture change** → update `docs/context/project-context.md` if the change is product-wide or structural.
2. **Implementation detail for one domain** → update or add the matching `docs/skills/*.md` file.
3. **Every significant code change** → add a dated file under `docs/changelog/` (see recent examples for tone and length).
4. **New domain agents will touch often** → add a `docs/skills` file, then a thin `.cursor/skills/<name>/SKILL.md` wrapper with a trigger-rich description.
5. **Do not revive** removed route families listed in `project-context.md` and `docs/skills/automation.md`.

## Skill index

| Skill | Use when |
|-------|----------|
| [authentication](skills/authentication.md) | App login, JWT, bcrypt |
| [security-credentials](skills/security-credentials.md) | Fernet MT5 secrets, redaction, what never leaves the server |
| [mt5-integration](skills/mt5-integration.md) | Local MetaTrader5 adapter / terminal paths |
| [mt5-ea-tick-bridge](skills/mt5-ea-tick-bridge.md) | Optional EA tick ingest websocket |
| [symbol-resolver](skills/symbol-resolver.md) | GOLD/XAUUSD aliases, broker symbol mapping |
| [international-risk-sizing](skills/international-risk-sizing.md) | Volume floor, pip vs point, risk preview |
| [trading-order-lifecycle](skills/trading-order-lifecycle.md) | Manual orders, conditional SL, retry/ATM, events |
| [candle-detector](skills/candle-detector.md) | Hammer / Shooting Star order helper |
| [trade-planner](skills/trade-planner.md) | Planner plans and pending-order cancellation |
| [scheduled-break-trade](skills/scheduled-break-trade.md) | User scheduled break tool |
| [automation](skills/automation.md) | Index of active strategy runtimes |
| [trap-reversal](skills/trap-reversal.md) | Double Trap Reversal FSM |
| [master-break](skills/master-break.md) | Master Break live + backtest |
| [websocket-live-state](skills/websocket-live-state.md) | `/ws/live` snapshots |
| [chart-datafeed](skills/chart-datafeed.md) | Backend candle caches (chartless UI) |
| [mongodb](skills/mongodb.md) | Motor DB layer and collections |
| [frontend-state-management](skills/frontend-state-management.md) | Zustand + React Query |
| [indian-mstock-workflow](skills/indian-mstock-workflow.md) | Indian market separation |
| [local-operations](skills/local-operations.md) | `mt5-platform.bat` lifecycle |
| [android-app](skills/android-app.md) | Native Android client |
| [ios-app](skills/ios-app.md) | Native iOS client |

## Architecture notes

- [local-runtime](architecture/local-runtime.md) — current Windows runtime
- [mac-runtime-plan](architecture/mac-runtime-plan.md) — **plan only**; bridge service is not implemented yet
