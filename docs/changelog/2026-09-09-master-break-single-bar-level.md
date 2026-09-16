# Master Break level from latest completed H6 only

## Summary

Master Break no longer uses two-bar `C2H`/`C2L`. Short level is the latest completed master **high**; long level is that candle’s **low**. While waiting for break, each new completed master replaces the level. M5 close-beyond + red/green signal arming is unchanged. Seed/backtest now require ≥2 master candles (was ≥3).
