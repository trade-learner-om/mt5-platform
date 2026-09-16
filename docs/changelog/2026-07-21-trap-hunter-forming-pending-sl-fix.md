# Trap Hunter forming pending-SL fix

- Live forming-M5 path no longer treats the R1 arming bar’s own OHLC as a pending stop-out (SHORT SL = R1 high previously always self-hit → phantom `SL_HIT` → two consecutive → `DISABLED`).
- After an R1 shift re-arm, recursive armed-bar processing passes `check_pending_sl=False` (same as the completed-bar arm path).
- Live runs register and look up by `broker_symbol` so ticks match; stop resolves requested or broker symbol aliases.
- Regression tests cover same-candle no self-SL, later-bar real SL, and broker-symbol run keys.
