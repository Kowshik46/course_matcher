"""
engine/weights.py — Base weights and reason-based dynamic adjustment.

Base weights sum to exactly 1.00.
Reason deltas are applied additively, then renormalized so the result
always sums to 1.0.

Param order (also used as canonical ordering elsewhere):
    placements, accreditation, brand, qs, course_depth, faculty, support, infra
"""
from __future__ import annotations

# ── Base weights (sum = 1.00) ──────────────────────────────────────────────
BASE_WEIGHTS: dict[str, float] = {
    "placements":    0.18,
    "accreditation": 0.15,
    "brand":         0.14,
    "qs":            0.13,
    "course_depth":  0.12,
    "faculty":       0.11,
    "support":       0.09,
    "infra":         0.08,
}

# ── Reason deltas (applied before renormalization) ─────────────────────────
REASON_DELTAS: dict[str, dict[str, float]] = {
    "Job Change":     {"placements": +0.06, "brand": +0.03},
    "Salary Hike":    {"placements": +0.06, "brand": +0.02},
    "Industry Shift": {"course_depth": +0.05, "placements": +0.03},
    "Move Abroad":    {"qs": +0.07, "accreditation": +0.04},
    "Others":         {},  # no change
}


def get_weights(reasons: list[str]) -> dict[str, float]:
    """
    Return a weight dict that sums to 1.0, adjusted for the given reasons.

    Parameters
    ----------
    reasons : list of selected reason strings, e.g. ["Job Change", "Salary Hike"]
              Unknown reasons are silently ignored (treated like "Others").

    Returns
    -------
    dict mapping param name → weight (floats summing to 1.0)
    """
    weights = dict(BASE_WEIGHTS)  # shallow copy — values are floats

    # Apply each reason's deltas additively
    for reason in reasons:
        deltas = REASON_DELTAS.get(reason, {})
        for param, delta in deltas.items():
            if param in weights:
                weights[param] += delta

    # Renormalize so weights always sum to 1.0
    total = sum(weights.values())
    if total <= 0:
        # Fallback: equal weights (should never happen with valid input)
        n = len(weights)
        return {k: 1.0 / n for k in weights}

    return {k: v / total for k, v in weights.items()}
