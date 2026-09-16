# Trend Pilot dual exit SL sync (position + opposite pending)

## Requirement

Irrespective of netting/hedging account type, while in position Trend Pilot must always maintain:

1. SL attached on the **running position**
2. An **independent opposite SL pending** at the **same price**

When the C1/C2 window rolls after candle completion, **both** legs must move to the updated (non-widening) SL.

## Fixes

- `_sync_exit_protection` always updates both legs; opposite pending is replaced when price drifts.
- Candle-close `apply_window` calls `_sync_exit_protection(..., raise_on_error=True)`.
- Broker `stopLoss=0` is ignored so Short SL is no longer wiped by the ratchet.
- Flip/recovery skips a second market order if the opposite leg already exists (avoids duplicate shorts on hedging).
