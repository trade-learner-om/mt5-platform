# Scheduled Trade bid candles and lifecycle logs

## Summary

Scheduled Break Trade live ExecCandle rolls now use **bid** (aligned with Master Break / MT5 charts) instead of mid, so chart-green/red signals match runtime detection. Primary placement still uses SL first with LIMIT fallback on Invalid price (unchanged). Backend INFO logs cover level break, signal candle / skip, SL / LIMIT place, fill, and TARGET/STOP exits. Scheduled Trade UI Notes always prefer `last_error` when present.
