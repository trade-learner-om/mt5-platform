# Fix ScheduledTradePanel api import path

## Summary

Vite failed to resolve `../api` from `src/components/scheduled-trade/ScheduledTradePanel.jsx` (that path points at `src/components/api`). Updated the import to `../../api` to match other nested component modules.
