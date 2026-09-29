# Remove strategy and FSM runtimes

Strategy engines and their UI are gone. Order placement, manual order runtime, trade planner, risk sizing, and watchlists stay.

Removed:

- Trap Reversal, Master Break, Scheduled Break Trade, and unmitigated-swings execution (web pages, REST routes, services, FSMs, tests)
- Indian strategy preview and PE→Stock→CE backtest
- FSM command center in the trading terminal
- Android/iOS Trap Reversal and Trend Pilot screens

Live ticks still drive watchlist prices, manual orders, deferred market-open orders, and trade planner execution.
