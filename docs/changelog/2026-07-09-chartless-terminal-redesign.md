# 2026-07-09 - Chartless Execution Terminal Redesign

- Removed the web `TradingChart` component and uninstalled `lightweight-charts` from `apps/frontend-react`.
- Added `framer-motion`, `lucide-react`, `clsx`, and `tailwind-merge` to support the new animated terminal shell.
- Introduced a context-based `ThemeProvider` with light, dark, and system modes using Tailwind's `dark` strategy and CSS variable-backed palettes in `apps/frontend-react/src/index.css`.
- Replaced the old web header treatment with a new `AppShell` featuring a collapsible desktop sidebar, mobile bottom navigation, top-level account and connectivity controls, and theme switching.
- Rebuilt the international trading workspace into a chartless execution terminal: animated live ticker/watchlist, embedded Trap Reversal command center, manual order ticket, and animated active-orders panel with live target/stop distance readouts.
- Refactored `TrapReversalDashboard` into a richer command center with animated H1 support/resistance proof lists, pulsing FSM state indicators, live price visibility, and responsive embedded/standalone layouts.
