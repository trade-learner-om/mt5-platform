# Trend Pilot active run: display broker server time

## Summary

C1/C2 candle timestamps and next H4 close on the active run card now display in MT5 broker server time instead of the browser local timezone (IST) or raw UTC.

## Changes

- `brokerTime.js` utility parses `broker_utc_offset` and formats timestamps in broker wall clock
- `TrendPilotActiveRunCard` shows broker timezone label on H4 window section
- Active run API includes `broker_utc_offset` and `broker_time_region` from account
