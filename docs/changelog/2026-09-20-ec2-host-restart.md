# 2026-09-20 — EC2 public DNS/IP after instance restart

Updated hosted API / Vite / CORS hosts to the new Windows EC2 address after restart:

- DNS: `ec2-13-232-110-145.ap-south-1.compute.amazonaws.com`
- IP: `13.232.110.145`

Touched: `api.js` `PRODUCTION_API_BASE`, `.env.production`, Vite `allowedHosts`, backend CORS defaults/examples, and local-operations docs.
