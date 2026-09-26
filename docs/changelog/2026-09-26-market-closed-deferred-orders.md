# Market-closed deferred pending orders

## Summary

When manual Place Order fails only because the market is closed (MT5 10018), the UI offers to save a local **Pending Order** (`DEFERRED_MARKET_OPEN`). Confirmed orders are not sent to the broker until after the next **Monday 04:30 IST**, then placed from the live stream loop. The Orders tab shows a Pending Orders section only when such rows exist; they are editable (entry/SL/target/qty/risk, bidirectional sizing) and cancellable until dispatch.
