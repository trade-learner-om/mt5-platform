# Trend Pilot: Hedging Account Reversal Fix

## Summary

Trend Pilot's 2× opposite pending stop assumed netting-style position accounting. On MT5 hedging accounts, an opposite deal opens a second independent position instead of closing the first, leaving duplicate exposure.

## Changes

- Expose `margin_mode` and `is_hedging_account` from `get_account_information` in `metaapi_client.py`.
- Cache account margin mode on `TrendPilotFSM` at start and restore.
- **Netting accounts**: 2× reversal pending stop at stored SL (unchanged).
- **Hedging accounts**: 1× opposite pending stop at stored SL (not 2×); on fill close the original leg, reconcile orphans, complete reversal. Position broker SL is cleared so exit is via the pending stop only.
- H4 roll replaces the pending reversal stop at the new level (2× netting, 1× hedging) after clearing any attached position SL.
- Gap recovery on hedging uses close-then-1×-market.
- `_reconcile_hedged_positions` closes orphan opposite legs when both LONG and SHORT tickets exist.
- Fix Trap Hunter startup import: `normalize_symbol` from `symbol_resolver`, not `risk`.

## Follow-up (2026-07-20)

Hedging exit protection was initially implemented with broker position SL only, which updated the position SL field but did not place a visible opposite pending stop in the Orders tab. Hedging now uses a **1× opposite pending stop** (with orphan cleanup on fill), matching the netting UX while avoiding the 2× duplicate-exposure bug.

## References

- [MT5 general trading concept (netting vs hedging)](https://www.metatrader5.com/en/terminal/help/trading/general_concept)
