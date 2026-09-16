# Master Break candle times stay broker faces

## Summary

`coerce_candle_time` now returns **naive broker-server faces** with no `astimezone` shifts (naive ISO / `+00:00` keep the written hour). Close-time backtest math and analytics compare faces consistently. Audit/trade ISO strings omit `+00:00` so they do not imply geographic UTC.
