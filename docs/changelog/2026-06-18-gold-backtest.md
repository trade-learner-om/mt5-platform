## 2026-06-18 — GOLD strategy revamp + backtest

### Changed

- Reworked the GOLD previous-day strategy to use broker D1 HTC/LTC only: M1 body-close arming, green/red setup candles, 100-pip SL rejection, 50% at breakeven R + 50% at final target R (0.01 lots use SL trailing), and clean-SL retry pivots up to two per direction per day.
- Removed manual High/Low to consider, user-selected trigger mode, and per-run manual target exits from the live GOLD workflow.
- If PD high or PD low was already wicked before start, that side is skipped for the broker day (no manual override).

### Added

- Shared strategy rules in `gold_strategy_rules.py` plus M1 replay simulator and date-range backtest engine.
- `POST /gold-strategy/backtest` and `GET /gold-strategy/backtest/{job_id}` for async historical replay against broker M1/D1 candles.
- Web GOLD page **Live | Backtest** tabs with delta-style summary stats, equity curve, and collapsible backtest trade ledger.

### Fixed

- Restored missing GOLD symbol resolver imports that broke `/gold-strategy` and live WebSocket snapshots.
- Fixed backtest simulator `OpenTrade` management initialization so replay jobs complete successfully.
- Backtest modal now defaults end date to today and start date to seven days earlier.
- Backtest setup includes minimum breakeven R (default 4) and final target R (default 20).
- Backtest trade rows now include global trade index, retry attempt labels, exit price, exit-leg timeline, and planned risk.
- EOD auto-close can be toggled off to carry positions overnight without new entries until flat.
- Equity curve matches delta CalendarSpread styling (gradient fill, zero-cross coloring, hover tooltip, side stats).
- Backtest results include a **Download JSON** action for raw job + result export.

### Fixed

- Backtest losses no longer exceed configured risk on stop/EOD exits (EOD exit capped at stop when auto-close is on).
- Backtest sizing/PnL uses broker symbol spec (contract size, tick value, volume step) from the feed account.
- Fixed inverted PnL sign for LONG/SHORT target exits (BUY/SELL side handling in `calc_pnl_from_price_move`).
