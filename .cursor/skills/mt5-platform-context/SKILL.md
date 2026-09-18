---
name: mt5-platform-context
description: >-
  Load canonical MT5 platform architecture, active routes, security rules, and
  documentation maintenance workflow. Use before any code change in this repo,
  or when the user asks about project structure, monorepo layout, or agent rules.
---

# MT5 Platform Context

## Required reading (in order)

1. `AGENTS.md`
2. `docs/context/project-context.md`
3. `docs/README.md` — skill index and when to update which doc
4. `docs/architecture/local-runtime.md`

## Then

Open the matching `docs/skills/*.md` for the domain you are changing. Prefer Cursor skills in `.cursor/skills/` for discovery.

## Do not

- Treat `docs/architecture/mac-runtime-plan.md` as implemented.
- Revive removed strategy route families listed in `docs/skills/automation.md`.
