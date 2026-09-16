# Revert Master Break manual open-offset (EEST xx:00)

## Summary

Removed `master_open_offset_minutes` / `phase_seconds` override. Broker EEST (UTC+3) H1 stamps are `xx:00`; H6 at `00/06/12/18` is correct. The prior default offset of 30 matched IST chart display, not a fetch bug. Aggregation still infers phase from source H1 opens. Range-fetch logs UTC vs IST faces for clarity.
