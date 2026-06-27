"""
app.py — Flask application: routes for student flow, admin CRUD, and healthz.

Architecture:
  Student intake → hard_filter (engine/) → score_programs (engine/) →
  generate_narrative (llm/) → results.html

The LLM never filters and never ranks.  All threshold/ranking logic is in
engine/ only.  The app boots and matches with zero Azure credentials set.
"""
from __future__ import annotations
import datetime
import sqlite3
from typing import Any

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import config
import db
from engine.filters import hard_filter
from engine.weights import get_weights
from engine.scoring import score_programs, PARAM_LABELS
from llm.narrative import generate_narrative

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Initialise DB schema on startup (CREATE TABLE IF NOT EXISTS — idempotent)
with app.app_context():
    db.init_db()


# ── Helpers ────────────────────────────────────────────────────────────────

def _coerce_pct(value: str | None) -> float:
    """
    Coerce a percent input to 0-100 float.
    Handles both '45' and '0.45' forms.
    """
    if not value:
        return 0.0
    v = float(value)
    # If someone sends 0.45 instead of 45, convert
    if 0.0 < v <= 1.0:
        v = v * 100.0
    return v


def _int_or(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except (ValueError, TypeError):
        return default


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    """Convert sqlite3.Row results to plain dicts."""
    return [dict(row) for row in rows]


# ── Healthz ────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


# ── Student flow ───────────────────────────────────────────────────────────

@app.get("/")
def intake():
    return render_template("intake.html")


@app.post("/recommend")
def recommend():
    f = request.form

    # Parse and coerce form inputs
    age = _int_or(f.get("age"), 0)
    city = (f.get("city") or "").strip()
    state = (f.get("state") or "").strip()
    level = (f.get("level") or "").strip()
    specialization = (f.get("specialization") or "").strip()
    mode = (f.get("mode") or "no_preference").strip()
    budget_inr = _int_or(f.get("budget_inr"), 0)
    qualification_pct = _coerce_pct(f.get("qualification_pct"))
    reasons_list = f.getlist("reasons")    # multi-select checkboxes
    reasons_csv = ",".join(reasons_list)
    derived_income = _int_or(f.get("derived_income"), 0)  # TODO: future use

    student_profile = {
        "age": age,
        "city": city,
        "state": state,
        "level": level,
        "specialization": specialization,
        "mode": mode,
        "budget_inr": budget_inr,
        "qualification_pct": qualification_pct,
        "reasons": reasons_csv,
    }

    # Log the lead (derived_income captured but NOT used in matching)
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO leads
              (age, city, state, level, specialization, mode,
               budget_inr, qualification_pct, reasons, derived_income)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (age, city, state, level, specialization, mode,
             budget_inr, qualification_pct, reasons_csv, derived_income or None),
        )
        conn.commit()

        # Fetch all programs for filtering
        rows = conn.execute("SELECT * FROM programs").fetchall()
    finally:
        conn.close()

    all_programs = _rows_to_dicts(rows)

    # Engine: filter → score → rank (no LLM involved)
    passing, eliminated = hard_filter(all_programs, student_profile)
    weights = get_weights(reasons_list)
    ranked = score_programs(passing, weights)

    # LLM narrative (fallback-safe — never blocks)
    narrative = generate_narrative(student_profile, ranked)

    return render_template(
        "results.html",
        ranked=ranked,
        eliminated_count=len(eliminated),
        total_count=len(all_programs),
        student=student_profile,
        weights=weights,
        param_labels=PARAM_LABELS,
        narrative=narrative,
        reasons_list=reasons_list,
    )


# ── Admin: programme CRUD ──────────────────────────────────────────────────

@app.get("/admin/programs")
def admin_list():
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM programs ORDER BY university, program_name"
        ).fetchall()
    finally:
        conn.close()
    return render_template("admin_list.html", programs=_rows_to_dicts(rows))


@app.get("/admin/programs/new")
def admin_new():
    return render_template("admin_form.html", program=None, action=url_for("admin_create"))


@app.post("/admin/programs")
def admin_create():
    data = _parse_program_form(request.form)
    conn = db.get_db()
    try:
        conn.execute(_INSERT_PROGRAM_SQL, _program_values(data))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin_list"))


@app.get("/admin/programs/<int:prog_id>/edit")
def admin_edit(prog_id: int):
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM programs WHERE id = ?", (prog_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return "Program not found", 404
    return render_template(
        "admin_form.html",
        program=dict(row),
        action=url_for("admin_update", prog_id=prog_id),
    )


@app.post("/admin/programs/<int:prog_id>")
def admin_update(prog_id: int):
    data = _parse_program_form(request.form)
    conn = db.get_db()
    try:
        conn.execute(_UPDATE_PROGRAM_SQL, (*_program_values(data), prog_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin_list"))


@app.post("/admin/programs/<int:prog_id>/delete")
def admin_delete(prog_id: int):
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM programs WHERE id = ?", (prog_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin_list"))


# ── SQL helpers (parameterized — no string formatting) ─────────────────────

_INSERT_PROGRAM_SQL = """
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

_UPDATE_PROGRAM_SQL = """
UPDATE programs SET
    university=?, program_name=?, level=?, specialization=?, mode=?,
    fee_inr=?, city=?, state=?, min_eligibility_pct=?, apply_url=?,
    placement_pct=?,
    brand_score=?, placements_score=?, course_depth_score=?, faculty_score=?,
    support_score=?, infra_score=?, accreditation_score=?, qs_score=?,
    approvals_text=?, notes=?
WHERE id=?
"""


def _parse_program_form(f) -> dict[str, Any]:
    return {
        "university": (f.get("university") or "").strip(),
        "program_name": (f.get("program_name") or "").strip(),
        "level": (f.get("level") or "").strip(),
        "specialization": (f.get("specialization") or "").strip(),
        "mode": (f.get("mode") or "online").strip(),
        "fee_inr": _int_or(f.get("fee_inr"), 0),
        "city": (f.get("city") or "").strip() or None,
        "state": (f.get("state") or "").strip() or None,
        "min_eligibility_pct": _coerce_pct(f.get("min_eligibility_pct")),
        "apply_url": (f.get("apply_url") or "").strip() or None,
        "placement_pct": _coerce_pct(f.get("placement_pct")) if f.get("placement_pct") else None,
        "brand_score": float(f.get("brand_score") or 0),
        "placements_score": float(f.get("placements_score") or 0),
        "course_depth_score": float(f.get("course_depth_score") or 0),
        "faculty_score": float(f.get("faculty_score") or 0),
        "support_score": float(f.get("support_score") or 0),
        "infra_score": float(f.get("infra_score") or 0),
        "accreditation_score": float(f.get("accreditation_score") or 0),
        "qs_score": float(f.get("qs_score") or 0),
        "approvals_text": (f.get("approvals_text") or "").strip() or None,
        "notes": (f.get("notes") or "").strip() or None,
    }


def _program_values(d: dict[str, Any]) -> tuple:
    return (
        d["university"], d["program_name"], d["level"], d["specialization"], d["mode"],
        d["fee_inr"], d["city"], d["state"], d["min_eligibility_pct"], d["apply_url"],
        d["placement_pct"],
        d["brand_score"], d["placements_score"], d["course_depth_score"], d["faculty_score"],
        d["support_score"], d["infra_score"], d["accreditation_score"], d["qs_score"],
        d["approvals_text"], d["notes"],
    )


if __name__ == "__main__":
    app.run(debug=True)
