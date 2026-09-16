# Fix Total Equity display for local MT5

## Problem

Header **Total Equity** always showed `$0.00` because the shell read `account.equity` / `available_margin`, while `/auth/me` returns `equity_balance`. `formatUsd(null)` also treated `null` as `0`.

## Fix

- Use `equity_balance` (and balance fallback) for international accounts.
- Treat missing equity as `--` instead of `$0.00`.
- Poll `GET /accounts/{id}/equity` every **15 seconds** against the local MT5 terminal (no account websocket).
- Keep polled equity in local header state (do **not** rewrite `me.accounts`), so account-list refreshes do not reset open settings forms.
- Trap Hunter settings hydrate once per modal open / settings payload, not on every `internationalAccounts` identity change.
