# Master Break: fix empty backtest toast

## Summary

App `notify(type, message)` expects two string args. Master Break was passing `{ type, message }`, so the toast rendered green with no text (only Dismiss).

## Changes

- `MasterBreakDashboard.jsx` and `MasterBreakSettingsModal.jsx` now call `onNotify("success"|"error", message)`.
