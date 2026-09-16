# Trend Pilot adaptive entry pullback reset

## Summary

- Fixed stale adaptive breach entries after a full pullback to C1C2 levels.
- When pre-entry stops revert from adaptive to C1C2, `post_h4_high` / `post_h4_low` are now re-seeded from the current tick so the next breach leg tracks fresh extremes instead of a prior peak.
- Adaptive entry on the breached side still uses the raw post-H4 extreme with no extra $10 buffer; only C1C2 entry/SL levels keep the buffer.

## Impact

- After pullback and re-breach (e.g. prior peak 4038, new breach high 4028), adaptive BUY/SELL STOP entry now arms at 4028 instead of staying at the stale 4038.
