from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

STRATEGY_TYPE = "master_break"
SETTINGS_KEY = "master_break"

ALLOWED_MASTER_TIMEFRAMES = frozenset({"H4", "H6", "H12", "D1"})
ALLOWED_EXEC_TIMEFRAMES = frozenset({"M1", "M5", "M15"})
TARGETS_SUM_TOLERANCE = 0.01

DEFAULT_TARGETS: list[dict[str, float]] = [
    {"r": 2.0, "qty_pct": 50.0},
    {"r": 4.0, "qty_pct": 50.0},
]


@dataclass
class MasterBreakTarget:
    r: float
    qty_pct: float

    def to_dict(self) -> dict[str, float]:
        return {"r": float(self.r), "qty_pct": float(self.qty_pct)}


@dataclass
class MasterBreakSettings:
    risk_amount: float = 100.0
    master_timeframe: str = "H6"
    exec_timeframe: str = "M5"
    breakeven_r: float = 1.0
    targets: list[MasterBreakTarget] = field(default_factory=lambda: [MasterBreakTarget(**item) for item in DEFAULT_TARGETS])

    @classmethod
    def from_mapping(cls, data: Optional[dict[str, Any]] = None) -> "MasterBreakSettings":
        raw = dict(data or {})
        targets_raw = raw.get("targets")
        if targets_raw is None:
            targets = [MasterBreakTarget(**item) for item in DEFAULT_TARGETS]
        else:
            targets = []
            for item in targets_raw:
                if not isinstance(item, dict):
                    raise ValueError("Each target must be an object with r and qty_pct")
                targets.append(
                    MasterBreakTarget(
                        r=float(item.get("r") or 0.0),
                        qty_pct=float(item.get("qty_pct") or 0.0),
                    )
                )
        settings = cls(
            risk_amount=float(raw.get("risk_amount") if raw.get("risk_amount") is not None else 100.0),
            master_timeframe=str(raw.get("master_timeframe") or "H6").upper().strip(),
            exec_timeframe=str(raw.get("exec_timeframe") or "M5").upper().strip(),
            breakeven_r=float(raw.get("breakeven_r") if raw.get("breakeven_r") is not None else 1.0),
            targets=targets,
        )
        settings.validate()
        return settings

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_amount": float(self.risk_amount),
            "master_timeframe": self.master_timeframe,
            "exec_timeframe": self.exec_timeframe,
            "breakeven_r": float(self.breakeven_r),
            "targets": [target.to_dict() for target in self.targets],
            "strategy_type": STRATEGY_TYPE,
        }

    def validate(self) -> None:
        if self.risk_amount <= 0:
            raise ValueError("risk_amount must be positive")
        if self.master_timeframe not in ALLOWED_MASTER_TIMEFRAMES:
            raise ValueError(f"master_timeframe must be one of {sorted(ALLOWED_MASTER_TIMEFRAMES)}")
        if self.exec_timeframe not in ALLOWED_EXEC_TIMEFRAMES:
            raise ValueError(f"exec_timeframe must be one of {sorted(ALLOWED_EXEC_TIMEFRAMES)}")
        if self.breakeven_r < 0:
            raise ValueError("breakeven_r must be >= 0")
        if not self.targets:
            raise ValueError("targets must contain at least one entry")
        for target in self.targets:
            if target.r <= 0:
                raise ValueError("each target r must be positive")
            if target.qty_pct < 0:
                raise ValueError("each target qty_pct must be >= 0")
        total_pct = sum(float(target.qty_pct) for target in self.targets)
        if abs(total_pct - 100.0) > TARGETS_SUM_TOLERANCE:
            raise ValueError(f"targets qty_pct must sum to 100% (got {total_pct})")
