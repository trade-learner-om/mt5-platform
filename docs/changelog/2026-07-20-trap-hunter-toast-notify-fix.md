# Trap Hunter / Trend Pilot toast notify argument fix

## Summary

Trap Hunter and Trend Pilot dashboards called `onNotify(message, type)` but `App.jsx` defines `notify(type, message)`. Errors rendered as green success toasts showing only the word `error` instead of the API error detail.

## Changes

- Fix `onNotify` call order in `TrapHunterDashboard.jsx`, `TrendPilotDashboard.jsx`, and `TrendPilotBacktestSettingsModal.jsx`.
- Add amber styling for `warning` flash toasts.
