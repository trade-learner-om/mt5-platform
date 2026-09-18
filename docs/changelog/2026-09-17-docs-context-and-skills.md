# Docs system: context, skills, and Cursor wrappers

## Summary

Built a maintainable documentation system for agents: `docs/README.md` index, new/updated `docs/skills` for gaps (Trap Reversal, Master Break, symbol resolver, candle detector, security, risk sizing, iOS), always-apply `.cursor/rules`, and thin `.cursor/skills` wrappers for auto-discovery.

## Changes

- Added `docs/README.md` with skill map and maintenance workflow.
- Split strategy detail into `trap-reversal.md` / `master-break.md`; `automation.md` is now the index + removed-route list.
- Added skills: `symbol-resolver`, `candle-detector`, `security-credentials`, `international-risk-sizing`, `ios-app`; expanded `android-app`.
- Fixed stale Trap Hunter / GOLD Strategy references in root README, tick-bridge skill, iOS README; aligned retryable-order docs with LIMIT+SL.
- Added `.cursor/rules/mt5-platform.mdc` and ten `.cursor/skills/*/SKILL.md` wrappers.
- Marked `docs/guides/cryptobridge-trend-pilot-porting.md` archived; adjusted mac-runtime-plan checklist wording for current strategies.
