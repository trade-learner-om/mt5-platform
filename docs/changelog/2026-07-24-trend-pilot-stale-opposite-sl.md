# Trend Pilot: cancel stale opposite SL pendings

## Problem

After an in-position SL ratchet/trail (e.g. Short SL 4109 → 4064), Trend Pilot placed a new opposite BUY STOP at the new SL but left the old BUY STOP at the previous price. Dedupe only removed duplicates *at the current SL*.

## Fix

`_dedupe_pending_stops_at_sl` now cancels opposite-side pendings whose price is not the current SL (same symbol/qty), then keeps a single order at the target. `_ensure_opposite_stop_at` runs this on every exit-protection sync (roll/restore/watchdog).
