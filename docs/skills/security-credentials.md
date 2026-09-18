# Security and Credentials

## Purpose

Centralize rules for application passwords, MT5 secrets, tokens, and log redaction.

## Two credential systems

| Kind | Storage | Recoverable? | Client exposure |
|------|---------|--------------|-----------------|
| App password | bcrypt hash on `users` | No | Never |
| MT5 password / token payload | Fernet ciphertext on `meta_accounts.api_token` (and related encrypted fields) | Yes, server-side only | Never |
| JWT access token | Issued at login; session id tracked | N/A | Bearer header only; never log |

## Implementation

- App auth: `apps/backend-python/app/auth.py`
- Fernet helpers: `apps/backend-python/app/services/encryption.py`, `apps/backend-python/app/services/secret_store.py`
- Env: `JWT_SECRET_KEY`, `FERNET_KEY` in `apps/backend-python/.env` (never commit)

Decrypt only inside backend services that need live MT5 or Mstock connectivity. Do not return decrypted MT5 credentials from any API, websocket, error payload, or frontend state.

## Redaction

Logs may include masked account ids, MT5 server names, route names, and validation details.  
Logs must **not** include plaintext passwords, decrypted credential payloads, Fernet ciphertext dumps, or JWT access tokens.

## Agent checklist

- [ ] No plaintext secrets in commits, fixtures, or changelog examples
- [ ] New endpoints that touch accounts do not echo `api_token` or password fields
- [ ] Diagnostics use masked login / error codes only
