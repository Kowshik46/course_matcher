"""
engine/filters.py — Hard constraint filtering.

A program PASSES only if ALL six rules hold.  Returns:
  (passing_programs, eliminated_with_reason)

All percent values are 0-100 (never 0-1).
All money values are plain integer rupees.
"""
from __future__ import annotations
from typing import Any


def hard_filter(
    programs: list[dict[str, Any]],
    student: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Apply all 6 hard-filter rules to *programs* against *student* profile.

    student dict keys expected:
        level           str   — "bachelors" | "masters" | "certification"
        specialization  str   — e.g. "Finance"
        budget_inr      int   — max fee student can pay
        qualification_pct float  — 0-100
        mode            str   — "online" | "offline" | "no_preference"
        city            str
        state           str

    Returns
    -------
    passing        : list of program dicts that passed every rule
    eliminated     : list of dicts  {program: <dict>, reason: <str>}
    """
    passing: list[dict[str, Any]] = []
    eliminated: list[dict[str, Any]] = []

    student_level = (student.get("level") or "").strip().lower()
    student_field = (student.get("specialization") or "").strip().lower()
    student_budget = int(student.get("budget_inr") or 0)
    student_qual = float(student.get("qualification_pct") or 0)
    student_mode = (student.get("mode") or "no_preference").strip().lower()
    student_city = (student.get("city") or "").strip().lower()
    student_state = (student.get("state") or "").strip().lower()

    for prog in programs:
        prog_level = (prog.get("level") or "").strip().lower()
        prog_field = (prog.get("specialization") or "").strip().lower()
        prog_fee = int(prog.get("fee_inr") or 0)
        prog_min_pct = float(prog.get("min_eligibility_pct") or 0)
        prog_mode = (prog.get("mode") or "").strip().lower()
        prog_city = (prog.get("city") or "").strip().lower()
        prog_state = (prog.get("state") or "").strip().lower()

        # Rule 1 — Level must match exactly
        if prog_level != student_level:
            eliminated.append({"program": prog, "reason": f"Level mismatch: program={prog_level}, student={student_level}"})
            continue

        # Rule 2 — Field: case-insensitive substring match in either direction
        # "Finance" matches "MBA Finance" and "MBA Finance" matches "Finance"
        if student_field not in prog_field and prog_field not in student_field:
            eliminated.append({"program": prog, "reason": f"Field mismatch: program={prog_field!r}, student={student_field!r}"})
            continue

        # Rule 3 — Budget: fee must not exceed student's budget
        if prog_fee > student_budget:
            eliminated.append({"program": prog, "reason": f"Over budget: fee=₹{prog_fee:,}, budget=₹{student_budget:,}"})
            continue

        # Rule 4 — Eligibility: program's minimum % must not exceed student's %
        # (program accepts students AT or BELOW its min threshold)
        if prog_min_pct > student_qual:
            eliminated.append({"program": prog, "reason": f"Eligibility: program requires {prog_min_pct}%, student has {student_qual}%"})
            continue

        # Rule 5 — Mode compatibility
        if student_mode == "online":
            if prog_mode not in ("online", "hybrid"):
                eliminated.append({"program": prog, "reason": f"Mode mismatch: student wants online/hybrid, program is {prog_mode}"})
                continue
        elif student_mode == "offline":
            if prog_mode not in ("offline", "hybrid"):
                eliminated.append({"program": prog, "reason": f"Mode mismatch: student wants offline/hybrid, program is {prog_mode}"})
                continue
        # "no_preference" — any mode passes Rule 5

        # Rule 6 — Location: only applies to non-online programs
        # Pure-online programs always pass location check
        if prog_mode != "online":
            # For offline/hybrid: city or state must match
            city_match = prog_city and student_city and prog_city == student_city
            state_match = prog_state and student_state and prog_state == student_state
            if not city_match and not state_match:
                eliminated.append({
                    "program": prog,
                    "reason": (
                        f"Location mismatch: program is in {prog.get('city')}/{prog.get('state')}, "
                        f"student is in {student.get('city')}/{student.get('state')}"
                    ),
                })
                continue

        passing.append(prog)

    return passing, eliminated
