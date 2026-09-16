# Local Runtime Architecture

The platform runs locally on Windows:

1. React frontend runs with Vite.
2. FastAPI backend runs in a Python virtual environment.
   MongoDB access now goes through a Motor-backed compatibility layer in the backend.
3. MongoDB runs locally.
4. MetaTrader 5 terminal runs locally and is accessed by the backend through the Python `MetaTrader5` package.

This avoids Docker because real MT5 terminal integration is local desktop software integration, not a container-native service.

To keep the local runtime responsive under live tick load, blocking MT5 terminal work is serialized through the backend MT5 session manager and the websocket/runtime hot path is offloaded from the main asyncio event loop into worker threads where needed. That worker-thread bridge now also wraps the route-facing market-data restore, refresh, reconcile, and pushed-tick ingestion entrypoints in `apps/backend-python/app/main.py`, while request-path MongoDB reads and writes have been moved onto awaited Motor calls for the main async API surface.
