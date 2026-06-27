"""
engine/scoring.py — Weighted scoring of filtered programs.

For each program:
    normalized_i = param_i / 10.0        (0..10 → 0..1)
    score        = Σ (weight_i * normalized_i)   for 8 params
    score_pct    = round(score * 100, 1)  (0..100, shown to user)

Ties: placement_pct DESC, then fee_inr ASC.

Returns a list of dicts, each containing the original program data PLUS:
    score_pct       float — overall score 0-100
    contributions   dict  — {param_name: contribution_pct} where
                            contribution_pct = weight_i * normalized_i * 100
"""
from __future__ import annotations
from typing import Any

# Canonical mapping from weight-key to program column name
PARAM_MAP: dict[str, str] = {
    "placements":    "placements_score",
    "accreditation": "accreditation_score",
    "brand":         "brand_score",
    "qs":            "qs_score",
    "course_depth":  "course_depth_score",
    "faculty":       "faculty_score",
    "support":       "support_score",
    "infra":         "infra_score",
}

# Human-readable display labels for the 8 params
PARAM_LABELS: dict[str, str] = {
    "placements":    "Placements",
    "accreditation": "Accreditation",
    "brand":         "Brand",
    "qs":            "QS Ranking",
    "course_depth":  "Course Depth",
    "faculty":       "Faculty",
    "support":       "Student Support",
    "infra":         "Infrastructure",
}


def score_programs(
    programs: list[dict[str, Any]],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    """
    Score and rank *programs* using *weights*.

    Parameters
    ----------
    programs : passing programs (output of hard_filter)
    weights  : weight dict from get_weights(), must sum to ~1.0

    Returns
    -------
    List of dicts (each program dict extended with score_pct and contributions),
    sorted by score_pct DESC, placement_pct DESC, fee_inr ASC.
    """
    scored: list[dict[str, Any]] = []

    for prog in programs:
        contributions: dict[str, float] = {}
        raw_score = 0.0

        for param_key, col_name in PARAM_MAP.items():
            raw_val = float(prog.get(col_name) or 0)
            normalized = raw_val / 10.0          # 0-10 → 0-1
            w = weights.get(param_key, 0.0)
            contribution = w * normalized         # 0-1
            contributions[param_key] = round(contribution * 100, 2)  # → 0-100
            raw_score += contribution

        score_pct = round(raw_score * 100, 1)

        result = dict(prog)  # copy all program fields
        result["score_pct"] = score_pct
        result["contributions"] = contributions
        scored.append(result)

    # Sort: score_pct DESC, placement_pct DESC, fee_inr ASC
    scored.sort(
        key=lambda p: (
            -p["score_pct"],
            -(float(p.get("placement_pct") or 0)),
            int(p.get("fee_inr") or 0),
        )
    )

    return scored
