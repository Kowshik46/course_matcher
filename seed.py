"""
seed.py — Load programs_seed.json into the SQLite database.

Idempotent: clears the programs table and reloads from JSON on every run.
Run with:  python seed.py

WARNING: The seed data contains SYNTHETIC PLACEHOLDER values.
University/provider names are real and public, but fees, eligibility,
placement %, and all 8 quality scores are fabricated for engine testing.
Do NOT surface these figures to real students.  See _meta.DATA_WARNING.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Ensure we can import db and config from the project root
sys.path.insert(0, str(Path(__file__).parent))

import db


SEED_FILE = Path(__file__).parent / "programs_seed.json"

INSERT_SQL = """
INSERT INTO programs (
    university, program_name, level, specialization, mode,
    fee_inr, city, state, min_eligibility_pct, apply_url,
    placement_pct,
    brand_score, placements_score, course_depth_score, faculty_score,
    support_score, infra_score, accreditation_score, qs_score,
    approvals_text, notes
) VALUES (
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?
)
"""


def seed() -> None:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    programs = data["programs"]

    db.init_db()
    conn = db.get_db()
    try:
        # Clear and reload — idempotent
        conn.execute("DELETE FROM programs")

        for p in programs:
            conn.execute(INSERT_SQL, (
                p["university"],
                p["program_name"],
                p["level"],
                p["specialization"],
                p["mode"],
                int(p["fee_inr"]),
                p.get("city"),
                p.get("state"),
                float(p["min_eligibility_pct"]),
                p.get("apply_url"),
                float(p["placement_pct"]) if p.get("placement_pct") is not None else None,
                float(p.get("brand_score", 0)),
                float(p.get("placements_score", 0)),
                float(p.get("course_depth_score", 0)),
                float(p.get("faculty_score", 0)),
                float(p.get("support_score", 0)),
                float(p.get("infra_score", 0)),
                float(p.get("accreditation_score", 0)),
                float(p.get("qs_score", 0)),
                p.get("approvals_text"),
                p.get("notes"),
            ))

        conn.commit()
        print(f"Seeded {len(programs)} programs into the database.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
