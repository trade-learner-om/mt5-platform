# 2026-07-10 - Terminal Dashboard Implementation

- Reworked the React web shell into a stricter execution terminal layout with a collapsible left sidebar, compact top bar, and full-height dashboard workspace.
- Replaced the earlier mixed terminal/cards composition with dedicated terminal components:
  - `PriceCell.jsx`
  - `LiveWatchlist.jsx`
  - `FSMCommandCenter.jsx`
  - `ActivePositions.jsx`
  - `TerminalDashboard.jsx`
  - `SettingsTerminalPage.jsx`
- Moved trap-reversal control and live engine state into a reusable FSM command-center component so the trading dashboard and standalone FSM page share the same route-backed logic.
- Simplified theming to a Tailwind `dark` class strategy managed by `ThemeProvider.jsx`, and removed the custom CSS variable terminal theme layer from `src/index.css`.
- Updated the international trading workspace to use the new dense three-column data grid instead of the earlier chartless-but-card-heavy layout.
- Restyled the Positions tab internals so pending orders, live positions, and broker history all render with the same terminal dark/light surfaces instead of the old sky-and-white tracker styling.
- Restored the manual order ticket to the terminal dashboard and introduced **Quick Order** as its default mode. Quick Order derives the latest completed M1/M3/M5 candle stop (buy: low minus one broker tick; sell: high plus one broker tick), refreshes the multi-account risk-size preview with live ticks, and recalculates the broker quote, stop, and quantity again immediately before placing a market order through `/orders/quick`.
- Corrected Quick Order to use the most recent **completed** M1, M3, or M5 candle rather than the forming candle. M3 is derived from the completed M1 bucket immediately preceding the current three-minute interval.
- Switched Tailwind to class-based dark mode so the shell toggle controls the rendered `dark:` utilities, then updated the order ticket, notification detail modal, and Trade Planner terminal surfaces with dark/light contrast-safe backgrounds, borders, inputs, and text.
- Fixed the terminal dashboard grid to use gap-safe fractional tracks across the full desktop width. Quick Order now loads its completed-candle stop only when the account, symbol, direction, or timeframe changes, while live ticks continue to refresh market entry and risk sizing without cancelling that request.
- Fixed Quick Order target handling: previews now include the active feed account and selected copy targets, bootstrap safely with only the active account, and an optional copy account can be unchecked without being restored by stale selection state.
- Made copy-target removal explicit in the ticket checkbox handler so an optional secondary account remains removed after its checkbox is cleared; only the required feed account stays locked.
