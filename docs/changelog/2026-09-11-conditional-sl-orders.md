# Conditional Manual SL orders

## Summary

Manual Place Order SL tickets can arm a Conditional order: the app waits for live price to cross a trigger (tick-based, no candle close), then places the normal broker BUY_STOP/SELL_STOP. Waiting orders use status `WAITING_TRIGGER` and appear in Stop Orders until triggered or cancelled.
