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

Local web access defaults to:

- UI: `http://localhost:5173`
- API / WS: `http://localhost:8000` and `ws://localhost:8000` (via `apps/frontend-react/.env.development`)

`apps/frontend-react/src/api.js` forces the local backend when the browser host is localhost/LAN, even if an older env still points at a hosted API.

Restore the hosted EC2 API from a local UI session — set in `apps/frontend-react/.env.local` (or temporarily in `.env.development`) and restart Vite:

```env
VITE_USE_PRODUCTION_API=true
```

## Hosted Amplify + Windows EC2

- UI: `https://main.d3inecn5vye1xf.amplifyapp.com`
- API: `http://ec2-13-201-137-73.ap-south-1.compute.amazonaws.com:8000` (also `http://13.201.137.73:8000`)
- Production builds embed the EC2 URL via `apps/frontend-react/.env.production` and `PRODUCTION_API_BASE` in `src/api.js`.

Public reachability on the Windows EC2 requires **both**:

1. AWS Security Group inbound TCP `8000`
2. Windows Firewall inbound TCP `8000` (SG alone is not enough)

```powershell
New-NetFirewallRule -DisplayName "MT5 Backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
```

Backend CORS defaults allow `https://main.d3inecn5vye1xf.amplifyapp.com` and `https://*.amplifyapp.com`. On the EC2 host, set matching `CORS_ORIGINS` / `CORS_ORIGIN_REGEX` in `apps/backend-python/.env` and restart uvicorn (`--host 0.0.0.0 --port 8000`).

**Mixed content:** Amplify serves HTTPS. Browsers block calls from that page to the current HTTP API until TLS is terminated on EC2 (or a HTTPS proxy). Until then, verify with:

```bash
curl http://ec2-13-201-137-73.ap-south-1.compute.amazonaws.com:8000/health
```

or a local Vite UI (`http://localhost:5173`) with `VITE_USE_PRODUCTION_API=true` / `VITE_API_BASE_URL` pointing at EC2.

When accessing from another machine on the LAN, open `http://<server-lan-ip>:5173`. The frontend rewrites the API host to that same LAN IP on port `8000` unless production mode is opted in.
