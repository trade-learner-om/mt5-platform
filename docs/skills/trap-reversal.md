# Trap Reversal

## Purpose

Document the Double Trap Reversal strategy runtime for international MT5 accounts.

## Implementation

Runtime: `apps/backend-python/app/services/trap_reversal_automation.py`  
Helpers: `apps/backend-python/app/services/trap_entry_helpers.py`  
Tick entry: `market_data_stream` → `TrapReversalManager.handle_price(symbol, tick)`

Do not revive removed strategy route families (see `docs/skills/automation.md`).

## Engine design

- H1 supports/resistances indexed once per start with `scipy.signal.find_peaks`.
- Forward-pass monotonic stack drops already-mitigated H1 levels before live start.
- Live routing is `O(1)` per symbol into a dedicated `DoubleTrapFSM`.
- Each FSM uses scalar prices and a tiny rolling M1 candle buffer (no pandas on the tick path).

### FSM sequence

1. `SEEKING_H1_SPIKE`
2. `WAITING_FOR_FIRST_PULLBACK`
3. `WAITING_FOR_TRAP_DROP`
4. `TRACKING_TRUE_CHOCH`
5. `WAITING_FOR_BREAKOUT`
6. `EXECUTION`

### Execution

- Long setups: stop loss at absolute low minus one broker point.
- Volume sized through broker-aware risk utilities (`docs/skills/international-risk-sizing.md`).
- Entries are pending `BUY LIMIT` via the local MT5 adapter.
- Nearest active H1 resistance above entry is the target.

## REST

- `POST /trap-reversal/start`
- `POST /trap-reversal/stop`
- `GET /trap-reversal/levels/{symbol}`
- `GET /trap-reversal/active`

## Frontend

- Command center: `apps/frontend-react/src/pages/TrapReversalDashboard.jsx`
- Terminal embed: `apps/frontend-react/src/components/terminal/FSMCommandCenter.jsx`
- Left panel: H1 support/resistance proof; right panel: polled FSM summaries (not on the websocket snapshot hot path).
