# Fix conditional SL risk-preview entry validation

## Summary

`/risk-preview/multi` now honors `conditional_order` / `trigger_price`, so conditional SELL/BUY no longer fail with "SL entry must be above/below current price". Create still requires a trigger; preview skips entry-vs-market while the trigger is being entered.
