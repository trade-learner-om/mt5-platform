# Configurable max signal candle pips for Scheduled Break Trade

## Summary

Scheduled Break Trade max signal-candle size (the SL-width gate) is now a create-time input `max_signal_candle_pips`, defaulting to 10 FX / 100 XAUUSD. Oversized signal candles are still skipped until a valid one forms.
