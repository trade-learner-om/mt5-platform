# 2026-09-19 — Allow EC2 hostname in Vite `allowedHosts`

Running the Vite UI on the Windows EC2 and opening it via the public DNS was blocked by Vite’s host check. Added `ec2-13-201-137-73.ap-south-1.compute.amazonaws.com`, the regional `.ap-south-1.compute.amazonaws.com` suffix, and the public IP to `server.allowedHosts` in `apps/frontend-react/vite.config.js`.
