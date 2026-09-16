# Trend Pilot duplicate short + missing SL fixes

## Cause

1. **Missing Short SL:** After the non-widening SL change, broker `stopLoss=0` (meaning no SL) was treated as a real level. For Shorts, `min(0, candidate)` forced SL to `0`, so `modify_position` never attached a protective stop.
2. **Two Shorts:** Dual exit (position SL + opposite pending) on hedging accounts filled the opposite Short, then recovery/flip placed another market Short.

## Fix

- Ignore broker/persisted SL `<= 0` in ratchet helpers.
- If the opposite side is already open, skip the flip market order and consolidate duplicate same-side hedging legs.
- Post-entry watchdog consolidates duplicate same-side positions and re-syncs exit protection.

## Tests

- `apps/backend-python/test_trend_pilot_levels.py` (ratchet treats `0` as unset)
