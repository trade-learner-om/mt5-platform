# MT5 EA Tick Bridge

## Purpose

Optionally push MT5 live ticks into the backend from an EA or local bridge. The backend also supports per-second local MT5 polling, so this bridge is only needed when EA-driven ticks are preferred.

## Backend Endpoint

Connect to:

```text
ws://<backend-host>:8000/ws/mt5/ticks?secret=<account-secret>&account_id=<login-or-account-db-id>
```

The account secret is generated and saved per international MT5 account. Open Manage Accounts in the web app and copy the `MT5 EA Tick URL` for the account that owns the EA. The backend rejects tick ingest connections when the account secret is missing or invalid.

## Tick Payload

Send one JSON object per tick:

```json
{ "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002, "time": "2026-06-18T03:30:00Z" }
```

or batch multiple ticks:

```json
{
  "ticks": [
    { "symbol": "EURUSD", "bid": 1.08, "ask": 1.08002, "time": "2026-06-18T03:30:00Z" },
    { "symbol": "XAUUSD", "bid": 4310.1, "ask": 4310.3, "time": "2026-06-18T03:30:00Z" }
  ]
}
```

## EA Pseudocode

MQL5 does not provide a universal built-in websocket client in every terminal setup. Use either an MQL5 websocket library, a raw socket helper that performs the websocket handshake, or a small local bridge process. The EA-side behavior should follow this shape:

```text
OnInit:
  read the per-account MT5 EA Tick URL copied from Manage Accounts
  open websocket with that URL
  start reconnect timer

OnTick:
  tick = SymbolInfoTick(_Symbol)
  payload = {
    symbol: _Symbol,
    bid: tick.bid,
    ask: tick.ask,
    time: TimeToString(tick.time, ISO-like UTC format)
  }
  websocket.send_json(payload)

OnTimer:
  if websocket disconnected:
    reconnect

OnDeinit:
  close websocket
```

## Operational Notes

- Attach the EA to every chart/symbol that must push ticks, or use one bridge process that subscribes to all required symbols.
- Keep the backend port `8000` reachable from the MT5 machine.
- Do not send ticks for unavailable broker symbols. If an invalid symbol is in the watchlist, the backend removes it when symbol lookup reports it unavailable.
- The backend routes accepted ticks through the same market stream used by alerts, Trap Reversal, Master Break, Scheduled Break Trade, manual order runtime, M1 candles, planner runtime, and `/ws/live` snapshots.
