# Trap Hunter backtest sanity tooling

## Timezone matrix

| Surface | Time shown | Notes |
|---|---|---|
| Backtest date range | UTC calendar days | `from_date` / `to_date` parsed as UTC day bounds |
| Summary max DD timestamps | Broker + UTC | Replaces IST-only display |
| Trade roll timeline | Broker server time | Uses account `broker_utc_offset` |
| Raw JSON | UTC `Z` strings | Stored engine truth |
| FundedNext chart | Broker server clock | Compare rolls after broker offset conversion |

## Backtest vs live parity

Backtest outcomes can diverge from live for expected reasons:

1. Backtest uses **completed** M5/H4 bars only; live can arm on forming M5.
2. No spread model — fills use exact entry/SL/T1 prices.
3. Historical OHLC vs live mid ticks `(bid+ask)/2`.
4. Symbol suffix mismatch (`XAUUSD` vs `XAUUSD.i`).
5. Stale Mongo candle cache.

## Tooling added

- Trade detail API returns `audit` with formula and chronology checks.
- Backtest detail includes `audit_context` and live parity notes.
- `GET /trap-hunter/backtest/{id}/candles?timeframe=M5|H4` for CSV export.
- Trade details modal: audit panel, Copy audit JSON, Export M5/H4 CSV.
- `scripts/verify_trap_hunter_backtest_trade.py` for CLI verification.

## T1 partial semantics

When `t1_partial_qty_pct` is 0%, T1 only moves SL to breakeven. No P/L is booked on the `T1_ACHIEVED` roll; profit is realized on exit (e.g. breakeven stop after T1).
