# 2026-09-19 — EC2 Vite UI must call same-host :8000 API

Opening the Vite UI at `http://ec2-…:5173` used `.env.development` (`localhost:8000`), so the browser called the client machine and failed with `ERR_CONNECTION_REFUSED` even though the EC2 backend was healthy. `api.js` now detects the EC2 public DNS/IP and points API/WS at `http://<same-host>:8000`.
