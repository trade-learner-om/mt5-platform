# SignalBridge Local MT5 Platform

SignalBridge Local MT5 Platform is a local-first trading management system for MetaTrader 5 workflows. It provides application authentication, encrypted MT5 credential storage, multi-account selection, live prices, watchlists, manual orders, price alerts, trade planning, automation, order tracking, and broker reconciliation.

The app is adapted from a reference SignalBridge workflow, but international MT5 connectivity is handled through a local Windows MetaTrader 5 terminal instead of MetaApi.cloud.

## Repository Structure

- `apps/backend-python` - FastAPI backend, MongoDB persistence, JWT sessions, bcrypt password hashes, Fernet-encrypted MT5 credentials, local MT5 adapter, order lifecycle, alerts, planner, and automation routes.
- `apps/frontend-react` - Vite React frontend using TailwindCSS and the backend REST/WebSocket APIs.
- `apps/android-app` - Native Kotlin/Jetpack Compose Android app for LAN access to the same backend APIs.
- `docs` - Architecture notes, AI-readable project context, implementation skills, changelog, and migration plans.
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
TRAP_HUNTER_LOG_LEVEL=DEBUG
```

Trap Hunter activity is logged under the `app.trap_hunter` logger with structured payloads (FSM rolls, M5 bars, broker orders, run lifecycle). On Windows: `findstr trap_hunter logs\backend.log`.

## Frontend Setup

```powershell
cd apps/frontend-react
npm install
copy .env.example .env
npm run dev
```

The frontend listens on port `5173`. When opened from another device on the same LAN, use `http://<server-lan-ip>:5173`; API calls default to `http://<server-lan-ip>:8000` unless `VITE_API_BASE_URL` is explicitly set.

## Android App

The native Android app lives in `apps/android-app`. Open that folder in Android Studio, let Gradle sync, and run the `app` configuration on a device connected to the same LAN as the backend.

On first launch the app asks for the primary host, such as `192.168.7.1:5173`, saves it locally, and checks it on every launch. If the saved host cannot be reached, the host setup screen is shown again. Backend API and WebSocket traffic are derived from the same hostname on port `8000`.

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

Start with:

- `docs/context/project-context.md`
- `docs/architecture/local-runtime.md`
- `docs/skills/mt5-integration.md`
- `docs/architecture/mac-runtime-plan.md`

Update `docs/changelog` for significant behavior changes.
