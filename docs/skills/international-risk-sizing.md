# International Risk Sizing

## Purpose

Size international MT5 orders so configured risk is never exceeded by rounding volume upward.

## Implementation

`apps/backend-python/app/services/risk.py`  
Used by order placement, risk preview, trap reversal, master break, scheduled trades, and planner.

## Rules

- Floor volume to broker `volumeStep` (`normalize_volume_to_risk`); never ceil past risk.
- Reject when configured risk is below the broker minimum volume’s risk.
- Prefer live MT5 tick value / volume constraints when available; otherwise infer pip value carefully.

## Gold / XAU pip vs point

| Concept | Typical size | Use for |
|---------|--------------|---------|
| Broker point / pippet | `0.01` | Point buffers (entry offsets, SL point pads) |
| Pip | `0.10` | SL pip distance and risk sizing for XAU/GOLD |

`pip_size_for_symbol` returns `0.10` for gold-family symbols. Do not treat `0.01` as one pip for risk math.

## Related routes

- `/risk-preview` and `/risk-preview/multi`
- Any path that calls `quantity_from_risk` / live pip-value helpers before `order_send`
