# Localhost-first frontend API base

## Summary

Local Vite sessions now target `http://localhost:8000` by default (`.env.development` + `api.js`). Opening the UI on localhost/LAN no longer silently calls `api.signalbridge.in`. Production remains in `.env.production` and `PRODUCTION_API_BASE`; restore it from a local UI with `VITE_USE_PRODUCTION_API=true`.
