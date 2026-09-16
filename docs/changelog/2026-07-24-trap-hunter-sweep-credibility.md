# Trap Hunter sweep credibility + R1 SL ±1 point

## Alignment

Matches the live Short example path:

1. After an H4 sweep confirms, a **3 completed M5** trap-wait clock starts.
2. Within that window, the first matching trap candle (Short=Red / Long=Green) arms R1.
3. If the clock expires with no trap: emit `SWEEP_EXPIRED`, clear `swept`, and require a re-sweep of the **sweeping M5 extreme** (Short = that bar’s high; Long = that bar’s low).
4. R1 levels: entry = trap low−1 / high+1 point; **SL = trap high+1 / low−1 point**.

## Files

- `trap_hunter_levels.py` — `MAX_TRAP_WAIT_BARS`; SL ± point
- `trap_hunter_fsm.py` — trap wait / expire / re-sweep extreme; UI snapshot fields
- Persistence + live card show trap-wait remaining
- Regression: user Short tape 04:00–04:35 in `test_trap_hunter_backtest.py`
