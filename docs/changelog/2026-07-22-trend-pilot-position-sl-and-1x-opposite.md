# Trend Pilot position SL + 1× opposite stop

## Summary

When in position, Trend Pilot now:

1. Attaches the stop-loss on the **open broker position** (`modify_position`)
2. Places a **1×** opposite pending stop at the same price (netting and hedging)

Previously the position SL was cleared and only a reverse pending was used (2× on netting).

## Details

- `_sync_exit_protection` / H4 roll use `_ensure_position_stop_loss_at` instead of clearing SL
- `_exit_stop_quantity` always returns position size (1×)
- Gap/recovery market flips close the open leg if needed, then open opposite with 1×
- UI reversal qty fallback is 1×
