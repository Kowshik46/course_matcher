"""
tests/test_engine.py — Acceptance tests for the deterministic engine.

Run with:  pytest tests/test_engine.py -v

All five acceptance tests from BUILD_PLAN.md §5.4 are covered here.
The test fixture uses the same programs_seed.json data that seed.py loads
into SQLite, keeping tests independent of the database.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# Make engine importable whether we run from repo root or tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from engine.filters import hard_filter
from engine.weights import BASE_WEIGHTS, get_weights
from engine.scoring import score_programs

# ── Load seed data as the shared fixture ──────────────────────────────────

SEED_PATH = Path(__file__).parent.parent / "programs_seed.json"


@pytest.fixture(scope="module")
def all_programs() -> list[dict]:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return data["programs"]


# ── Base student profile for the worked example ───────────────────────────

BASE_STUDENT = {
    "level": "masters",
    "specialization": "Finance",
    "budget_inr": 300000,
    "qualification_pct": 45,
    "mode": "online",
    "city": "Bengaluru",
    "state": "Karnataka",
}

BASE_REASONS = ["Job Change", "Salary Hike"]


# ── Test 1 — Worked example returns non-empty list; placements weight highest
def test_worked_example_non_empty_and_placements_highest(all_programs):
    """
    Masters / Finance / Bengaluru / online / ₹3,00,000 / 45% /
    Job Change + Salary Hike → non-empty ranked list with placements
    having the highest weight in the final vector.
    """
    passing, eliminated = hard_filter(all_programs, BASE_STUDENT)
    assert len(passing) > 0, "Worked example must return at least one passing program"

    weights = get_weights(BASE_REASONS)
    ranked = score_programs(passing, weights)

    assert len(ranked) > 0, "score_programs must return non-empty list"

    # Placements must have the highest weight
    max_param = max(weights, key=lambda k: weights[k])
    assert max_param == "placements", (
        f"Expected placements to have highest weight, got {max_param}. "
        f"Weights: {weights}"
    )

    # Confirm expected survivors (from seed _meta note)
    surviving_universities = {r["university"] for r in ranked}
    expected = {
        "JAIN Online",
        "Amity University Online",
        "Manipal University Jaipur (Online)",
        "Chandigarh University Online",
        "LPU Online",
        "DY Patil University (Online)",
    }
    assert expected.issubset(surviving_universities), (
        f"Expected all of {expected} to survive. Got: {surviving_universities}"
    )

    # NMIMS must be eliminated (min_eligibility_pct=50 > student 45%)
    nmims_survivors = [r for r in ranked if "NMIMS" in r["university"] and r["specialization"] == "Finance"]
    assert len(nmims_survivors) == 0, "NMIMS Finance (min 50%) must be filtered out for a 45% student"


# ── Test 2 — Dropping budget shrinks survivor set
def test_lower_budget_shrinks_survivors(all_programs):
    """
    Budget ₹1,00,000 must produce fewer survivors than ₹3,00,000.
    """
    student_full = dict(BASE_STUDENT, budget_inr=300000)
    student_low = dict(BASE_STUDENT, budget_inr=100000)

    passing_full, _ = hard_filter(all_programs, student_full)
    passing_low, _ = hard_filter(all_programs, student_low)

    assert len(passing_low) < len(passing_full), (
        f"Lower budget should shrink survivors. "
        f"₹3L: {len(passing_full)}, ₹1L: {len(passing_low)}"
    )


# ── Test 3 — Raising eligibility bar (student at 40%) drops programs requiring ≥45%
def test_lower_qualification_drops_programs(all_programs):
    """
    Student at 40% qualification must get fewer or equal survivors compared to
    a student at 45%, because programs requiring exactly 45% are now excluded.
    """
    student_45 = dict(BASE_STUDENT, qualification_pct=45)
    student_40 = dict(BASE_STUDENT, qualification_pct=40)

    passing_45, _ = hard_filter(all_programs, student_45)
    passing_40, _ = hard_filter(all_programs, student_40)

    # Programs with min_eligibility_pct=45 pass for a 45% student but not a 40% student
    programs_req_45 = [p for p in all_programs if float(p.get("min_eligibility_pct") or 0) == 45]
    assert len(programs_req_45) > 0, "Seed must contain programs with min_eligibility_pct=45 to exercise this test"

    assert len(passing_40) < len(passing_45), (
        f"Student at 40% should get fewer survivors than at 45%. "
        f"45%: {len(passing_45)}, 40%: {len(passing_40)}"
    )


# ── Test 4 — No reasons → base weights exactly
def test_no_reasons_returns_base_weights():
    """
    Calling get_weights([]) must return weights that exactly match BASE_WEIGHTS
    (after renormalization, which is a no-op when no deltas are applied).
    """
    weights = get_weights([])

    base_total = sum(BASE_WEIGHTS.values())
    for param, base_w in BASE_WEIGHTS.items():
        expected = base_w / base_total   # renormalized base
        actual = weights[param]
        assert abs(actual - expected) < 1e-9, (
            f"Param {param}: expected {expected}, got {actual}"
        )


# ── Test 5 — Deterministic: same input → same ordering
def test_deterministic_ordering(all_programs):
    """
    Running the engine twice on the same input must yield identical ordering.
    """
    weights = get_weights(BASE_REASONS)

    passing1, _ = hard_filter(all_programs, BASE_STUDENT)
    ranked1 = score_programs(passing1, weights)

    passing2, _ = hard_filter(all_programs, BASE_STUDENT)
    ranked2 = score_programs(passing2, weights)

    ids1 = [p.get("university") + "|" + p.get("program_name") for p in ranked1]
    ids2 = [p.get("university") + "|" + p.get("program_name") for p in ranked2]

    assert ids1 == ids2, (
        f"Engine must be deterministic. Run1: {ids1}, Run2: {ids2}"
    )
