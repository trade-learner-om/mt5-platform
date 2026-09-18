# Candle Detector

## Purpose

Place Order helper for international MT5 accounts: scan recent completed candles for Hammer or Shooting Star and prefill an `SL` ticket.

## Implementation

Patterns: `apps/backend-python/app/services/candle_patterns.py`  
Route: `POST /orders/candle-detector/preview` in `apps/backend-python/app/main.py`

Scans the last five **completed** broker candles. Final sizing and placement still go through `/risk-preview/multi` and `POST /orders`.

## Mapping

| Pattern | Side | Suggested entry | Suggested stop |
|---------|------|-----------------|----------------|
| Hammer | `BUY` | candle high + 1 point | candle low − 1 point |
| Shooting Star | `SELL` | candle low − 1 point | candle high + 1 point |

Stop loss stays editable in the ticket. Point size comes from broker symbol specification (`point` / `tickSize` / `digits`).

## Pattern heuristics

- Body must be small relative to range (`body < 0.2 * range`).
- Rejection wick must dominate the opposite wick.
- Optional minimum candle range in points (default 15) when point size is known.
