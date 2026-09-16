# Local Operations

## Purpose

Manage the local backend and frontend servers from a single Windows command.

## Implementation

The command lives at `scripts/mt5-platform.bat` and supports:

- `mt5-platform start`
- `mt5-platform stop`
- `mt5-platform restart`
- `mt5-platform status`

The script starts FastAPI on `0.0.0.0:8000` and Vite on `0.0.0.0:5173` in separate terminal windows, so the app is reachable from other devices on the same LAN when the firewall allows those ports. It can create missing `.env` files from examples, create the backend virtual environment, install backend dependencies, generate local development secrets for placeholder `JWT_SECRET_KEY` and `FERNET_KEY` values via `scripts/generate_backend_secret.py`, and install frontend dependencies when `node_modules` is missing.

## Dependencies

- Windows Command Prompt or PowerShell
- Python launcher `py` or a default `python` executable that can create virtual environments
- Node.js and npm
- Local MongoDB
- Local MetaTrader 5 terminal

## Notes

Generated secrets are local development values stored in `apps/backend-python/.env`. Do not commit `.env`.

When accessing from another machine, open `http://<server-lan-ip>:5173`. The frontend API helper uses the browser host by default, so it will call `http://<server-lan-ip>:8000` unless `VITE_API_BASE_URL` is explicitly set.
