# Rename shared candle-gap log (drop Trend Pilot branding)

## Summary

`_warn_large_candle_gaps` in `candle_history` now logs `candle gap …` instead of `Trend Pilot candle gap …`, since Master Break and other callers share that helper.
