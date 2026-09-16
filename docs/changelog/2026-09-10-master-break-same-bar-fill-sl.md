# Fix Master Break same-bar fill+SL float(None)

## Summary

Same-bar `FILLED` then `STOPPED_OUT` called `reset_to_seeking()` before event handlers ran, so the open-trade snapshot stored `fsm.entry` as `None` and `float(trade["entry"])` crashed. Handlers now read entry/SL/qty from the event payload (with safe `as_float`), and a regression covers fill+stop on one M5 bar.
