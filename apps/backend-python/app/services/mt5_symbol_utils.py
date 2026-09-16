from typing import Optional

from .symbol_resolver import normalize_symbol


def mt5_symbol_candidates(requested: str) -> list[str]:
    requested = str(requested or "").strip()
    candidates: list[str] = []
    for candidate in (requested, requested.upper(), requested.lower()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def match_available_symbol_name(requested: str, available_names: list[str]) -> Optional[str]:
    needle = normalize_symbol(requested)
    for name in available_names:
        cleaned = str(name or "").strip()
        if cleaned and normalize_symbol(cleaned) == needle:
            return cleaned
    return None
