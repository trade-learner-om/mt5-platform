# Local Runtime Architecture

The platform runs locally on Windows:

1. React frontend runs with Vite.
2. FastAPI backend runs in a Python virtual environment.
   MongoDB access now goes through a Motor-backed compatibility layer in the backend.
3. MongoDB runs locally.
4. MetaTrader 5 terminal runs locally and is accessed by the backend through the Python `MetaTrader5` package.

This avoids Docker because real MT5 terminal integration is local desktop software integration, not a container-native service.

To keep the local runtime responsive under live tick load, blocking MT5 terminal work is serialized through the backend MT5 session manager. Route-facing live-stream restore, refresh, reconcile, and tick ingest hop onto `market_data_stream`'s dedicated tick loop rather than a throwaway `asyncio.run` worker loop, because `asyncio.Lock` and poll tasks cannot be reused across loops. Request-path MongoDB reads and writes use awaited Motor calls on the async API surface.
