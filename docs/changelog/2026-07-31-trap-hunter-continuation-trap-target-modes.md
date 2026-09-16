# Trap Hunter: continuation trap + target modes

## Behavior

- After a sweep-TF extreme is taken, **operational** bars build the trap. Same-color continuation bars update `post_trap_extreme` (no 3-bar trap expiry).
- Opposite-color ops bar arms the order:
  - **Short:** entry = signal low − 1pt; SL = post-trap high + 1pt
  - **Long:** entry = signal high + 1pt; SL = post-trap low − 1pt
- After square-off, same sweep-TF window re-entry requires an ops **body close** beyond the extreme reached through that trade.
- Logic is TF-agnostic: always uses `settings.sweep_timeframe` and `settings.operational_timeframe`.

## Targets / BE

| Field | Meaning |
|-------|---------|
| `target_mode` | `r_multiple` (default) or `sweep_candle` (opposite extreme of the anchored sweep-TF candle) |
| `t1_r_multiple` | Exit R when mode = `r_multiple` |
| `be_r_multiple` | R at which SL → BE (+ optional partial %); independent of target |
| `t1_partial_qty_pct` | Partial quantity booked at the BE event |

## Surface

- Settings modal + dashboard: target mode selector, BE at (R), TF-aware trap/re-entry copy.
- Live runs, backtest snapshots, audit context, and API schemas persist the new fields.
