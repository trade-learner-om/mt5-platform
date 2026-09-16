# Indian PE→Stock→CE monthly cycle backtest

## What shipped

- F&O equity stock typeahead (`kind=fno_equity`) on the Indian workspace.
- Backtest: sell monthly PE at −10% of spot → on strike hit, square PE, buy 1 lot stock, sell monthly CE at +10%.
- Expiry: CE ITM closes stock+CE and restarts with a new PE; CE OTM keeps stock and sells the next monthly CE.
- Option fills from mStock historical candles; missing bars emit `DATA_GAP` (no synthetic premiums).
- Monthly expiries only (stock options have no weeklies).

## APIs

- `POST /indian/pe-cycle/backtest`
- `GET /indian/pe-cycle/backtests`
- `GET /indian/pe-cycle/backtest/{id}`
- `DELETE /indian/pe-cycle/backtest/{id}`
