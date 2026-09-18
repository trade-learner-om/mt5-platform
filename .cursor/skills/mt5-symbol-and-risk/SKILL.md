---
name: mt5-symbol-and-risk
description: >-
  Per-account broker symbol aliases and international risk/volume sizing
  (pip vs point for GOLD/XAU). Use when resolving symbols, editing
  symbol_aliases, risk preview, or quantity_from_risk.
---

# Symbol Resolver and Risk

Read first:

1. `docs/skills/symbol-resolver.md`
2. `docs/skills/international-risk-sizing.md`

Key code: `symbol_resolver.py`, `risk.py`. Floor volume to `volumeStep`; never round risk up. For XAU/GOLD, `0.01` is a point and `0.10` is one pip.
