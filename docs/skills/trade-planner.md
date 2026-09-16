# Trade Planner

## Purpose

Preserve the reference app's trade planner workflow for deriving entry, stop, targets, risk, account allocation, and optional auto-execution.

## Implementation

Planner routes live in `apps/backend-python/app/main.py` and planner logic lives in:

- `apps/backend-python/app/services/trade_planner.py`
- `apps/backend-python/app/services/trade_planner_runtime.py`

Plans are stored in `trade_plans`. Planner live execution depends on `/ws/live` price updates and the local MT5 compatibility adapter for symbol specifications and order placement.

New plans default to execution-enabled. When execution is turned off, a plan is deactivated, or a plan is deleted, linked pending planner orders identified by `planner_context.plan_id` must be cancelled at the broker first. Filled/open positions are not closed automatically by planner deactivation or deletion.
