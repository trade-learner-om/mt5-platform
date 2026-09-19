# 2026-09-19 — Fill blank right side on trading terminal

The Watchlist page wrapped `InternationalMarketWorkspace` in a row flex `main` without giving the dashboard `w-full`/`flex-1`, so the three-column grid only sized to content and left a large empty strip on wide screens. The dashboard root now stretches to the full shell width.
