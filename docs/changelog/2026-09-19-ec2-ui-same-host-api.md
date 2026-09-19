# 2026-09-19 — EC2 Vite UI must call same-host :8000 API

Opening the Vite UI at `http://ec2-…:5173` used `.env.development` (`localhost:8000`), so the browser called the client machine and failed with `ERR_CONNECTION_REFUSED` even though the EC2 backend was healthy. `api.js` now detects the EC2 public DNS/IP and points API/WS at `http://<same-host>:8000`.

Follow-up: live `/health` returned 200 without `Access-Control-Allow-Origin` for the Vite EC2 origin (CORS error in the browser). Config now always merges required Amplify/EC2 Vite origins and regex parts even when `.env` overrides `CORS_ORIGINS` with an older list — restart the backend after pull.
