---
name: mt5-orders-and-manual-runtime
description: >-
  Manual order placement, conditional SL, retryable LIMIT/SL, automatic trade
  management, modify/cancel/close, and order events. Use when editing orders,
  manual_order_runtime, Place Order ticket, or Positions activity.
---

# Orders and Manual Runtime

Read first:

1. `docs/skills/trading-order-lifecycle.md`
2. `docs/skills/candle-detector.md` (if touching Candle Detector)
3. `docs/skills/international-risk-sizing.md` (if touching sizing)

Key code: `apps/backend-python/app/services/manual_order_runtime.py`, `order_placement.py`, `candle_patterns.py`.

Strategy-owned orders (`scheduled_trade_id`, trap/planner contexts) are skipped by manual retry/ATM.
