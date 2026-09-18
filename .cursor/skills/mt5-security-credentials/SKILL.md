---
name: mt5-security-credentials
description: >-
  bcrypt app passwords, Fernet MT5 encryption, JWT sessions, and log redaction.
  Use when touching auth, account creation, secret_store, encryption, or any
  code that might expose credentials.
---

# Security and Credentials

Read first: `docs/skills/security-credentials.md` and `docs/skills/authentication.md`.

Never return decrypted MT5 credentials through APIs, websockets, logs, frontend state, or errors. Do not commit `.env` secrets.
