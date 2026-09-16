# Agent Rules

This repository is designed to be maintained by human and AI coding agents.

## Required Reading

Before coding:

1. Read `docs/context/project-context.md`.
2. Read any relevant files in `docs/skills`.
3. Preserve the architecture described in the context documentation.

## Change Rules

- Update `docs/changelog` after every significant code change.
- After completing a code change, commit and push to `origin` unless the user explicitly asks not to push.
- Never store plaintext application passwords or plaintext MT5 passwords.
- Do not expose decrypted MT5 credentials through APIs, logs, frontend state, or errors.
- Prefer reusable services over duplicated logic.
- Maintain type safety in Python and TypeScript code.
- Keep backend routes thin and put business logic in services.
- Keep frontend API access in `src/services` and server state in React Query.
- Add focused tests when behavior becomes risky or shared.

## Local Runtime

The backend runs directly on Windows with a locally installed MetaTrader 5 terminal. Do not add Docker assumptions unless the architecture is explicitly changed.
