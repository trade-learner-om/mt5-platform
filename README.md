# SignalBridge Local MT5 Platform

SignalBridge Local MT5 Platform is a local-first trading management system for MetaTrader 5 workflows. It provides application authentication, encrypted MT5 credential storage, multi-account selection, live prices, watchlists, manual orders, price alerts, trade planning, automation, order tracking, and broker reconciliation.

The app is adapted from a reference SignalBridge workflow, but international MT5 connectivity is handled through a local Windows MetaTrader 5 terminal instead of MetaApi.cloud.

## Repository Structure

- `apps/backend-python` - FastAPI backend, MongoDB persistence, JWT sessions, bcrypt password hashes, Fernet-encrypted MT5 credentials, local MT5 adapter, order lifecycle, alerts, planner, and strategy routes (Trap Reversal, Master Break, Scheduled Break Trade).
- `apps/frontend-react` - Vite React chartless terminal using TailwindCSS and the backend REST/WebSocket APIs.
- `apps/android-app` - Native Kotlin/Jetpack Compose Android client (production API by default).
- `apps/ios-app` - Native SwiftUI iOS client with parity goals vs Android.
- `docs` - Architecture notes, AI-readable project context, implementation skills, changelog, and migration plans. Start at `docs/README.md`.
- `scripts` - Local Windows helper scripts for starting, stopping, and diagnosing the platform.
- `shared` - Reserved for future shared contracts or generated assets.

## Runtime Model

This project is designed for a local Windows runtime when using direct MT5 integration. The Python `MetaTrader5` package communicates with a locally installed MetaTrader 5 terminal through desktop IPC, so the backend must run on the same Windows machine as the terminal.

For macOS planning, see `docs/architecture/mac-runtime-plan.md`. The recommended Mac approach is a Mac UI/backend with a small Windows MT5 bridge service.

Docker is intentionally not used for the direct MT5 runtime because MT5 terminal integration is local desktop software integration.

## Prerequisites

- Windows for direct local MT5 mode.
- Python 3.12+.
- Node.js 20+.
- MongoDB running locally.
- MetaTrader 5 installed on the machine running the backend.
- A detected MT5 terminal path for each MT5 account during account creation. Use one unique MT5 terminal installation/copy per account when using multiple accounts.

## Backend Setup

```powershell
cd apps/backend-python
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Generate a Fernet key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set these values in `apps/backend-python/.env`:

```env
JWT_SECRET_KEY=replace-with-a-strong-secret
FERNET_KEY=replace-with-generated-fernet-key
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=mt5_platform
```

Start the API:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI is available at `http://localhost:8000/docs`.

### Backend logs

By default, backend logs are written to `apps/backend-python/logs/backend.log` (rotating; console output is off). Useful env vars in `apps/backend-python/.env`:

```env
LOG_FILE=logs/backend.log
LOG_TO_CONSOLE=false
LOG_LEVEL=INFO
LOG_FORMAT=text
```

Strategy and MT5 adapter logs use the normal backend logger hierarchy. Never log MT5 passwords or decrypted credentials.

## Frontend Setup

```powershell
cd apps/frontend-react
npm install
copy .env.example .env
npm run dev
```

The frontend listens on port `5173`. Open `http://localhost:5173`; API/WS default to `http://localhost:8000` via `.env.development`. To point a local UI at production again, set `VITE_USE_PRODUCTION_API=true` and restart Vite. Production builds still use `.env.production`.

## Mobile Apps

- Android: `apps/android-app` (Android Studio). Default build targets `https://api.signalbridge.in` / `wss://api.signalbridge.in/ws/live`. See `docs/skills/android-app.md`.
- iOS: `apps/ios-app` (Xcode). Same production hosts by default. See `docs/skills/ios-app.md` and `apps/ios-app/README.md`.

LAN host setup remains available for non-fixed builds. Mobile clients may still contain stale GOLD Strategy / Trend Pilot API calls against removed backends — do not restore those routes.

## Local Platform Commands

The `scripts/mt5-platform.bat` helper can manage both local servers:

```powershell
mt5-platform start
mt5-platform status
mt5-platform restart
mt5-platform stop
```

The script can create missing environment files from examples, create the backend virtual environment, install missing dependencies, and generate local development values for placeholder secrets.

## MT5 Notes

- Add each MT5 account with login, password, server, and the terminal executable path for the terminal instance logged into that account.
- For multiple MT5 accounts, copy/install MT5 into separate folders so each account has a unique terminal executable path.
- Run `mt5-diagnose` to verify that the backend Python environment can see the expected MT5 terminal.

## Security Model

- Application passwords are stored as bcrypt hashes and cannot be recovered.
- MT5 credentials are encrypted at rest with Fernet.
- MT5 passwords are never returned to the frontend.
- JWT access tokens authenticate application sessions.
- `.env` files, virtual environments, build outputs, and local logs are ignored by Git.

## Documentation

Start with `docs/README.md`, then:

- `docs/context/project-context.md`
- `docs/architecture/local-runtime.md`
- Matching files under `docs/skills/`
- `docs/architecture/mac-runtime-plan.md` (plan only; not implemented)

Update `docs/changelog` for significant behavior changes. Cursor agents also load thin wrappers from `.cursor/skills/`.
