# Authentication

## Purpose

Authenticate application users independently from MT5 credentials.

## Implementation

Application passwords are hashed with bcrypt in `apps/backend-python/app/auth.py`. JWT access tokens are created after successful registration or login and verified by `get_current_user`.

MT5 credentials are not part of the token. They remain encrypted in MongoDB and are decrypted server-side only when MT5 connectivity is needed.

Request and response diagnostics must redact password and token fields. Logs may include usernames, MT5 account numbers, servers, validation details, and request IDs, but never plaintext passwords or access tokens.

## Dependencies

- `passlib[bcrypt]`
- `python-jose[cryptography]`
- `JWT_SECRET_KEY` in backend `.env`

## Usage Example

1. User posts `username` and `password` to `/auth/login`.
2. Backend verifies the bcrypt hash.
3. Backend returns an access token and user profile without secrets.
4. Frontend attaches `Authorization: Bearer <token>` to authenticated API calls.
