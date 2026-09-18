# 2026-09-18 — Wire Amplify UI to Windows EC2 HTTP API

Hosted frontend now targets the new Windows EC2 backend.

## Frontend

- `PRODUCTION_API_BASE` and `.env.production` → `http://ec2-13-201-137-73.ap-south-1.compute.amazonaws.com:8000`
- Amplify hosts (`*.amplifyapp.com`, including `main.d3inecn5vye1xf.amplifyapp.com`) resolve to that API base
- HTTPS pages no longer rewrite the EC2 HTTP URL back to SignalBridge (mixed content may still block until TLS)

## Backend

- Default CORS includes `https://main.d3inecn5vye1xf.amplifyapp.com` and `https://*.amplifyapp.com`
- Windows EC2 needs Security Group **and** Windows Firewall TCP 8000; uvicorn must bind `0.0.0.0`
