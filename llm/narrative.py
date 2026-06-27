"""
llm/narrative.py — Generate a personalized explanation for the ranked shortlist.

The LLM NEVER filters, NEVER ranks — it only explains an already-ordered result.
If Azure creds are missing or the API call fails, a deterministic template
is returned.  This function must NEVER block or raise — it always returns a str.
"""
from __future__ import annotations
import json
import logging
from typing import Any

import config

logger = logging.getLogger(__name__)


def _top_two_params(contributions: dict[str, float]) -> list[str]:
    """Return the two param keys with the highest contribution values."""
    from engine.scoring import PARAM_LABELS
    sorted_params = sorted(contributions.items(), key=lambda x: -x[1])
    return [PARAM_LABELS.get(k, k) for k, _ in sorted_params[:2]]


def _deterministic_fallback(
    student_profile: dict[str, Any],
    ranked_programs: list[dict[str, Any]],
) -> str:
    """
    Build a plain-language explanation from the ranked data without the LLM.
    Always succeeds.
    """
    if not ranked_programs:
        return (
            "No programs matched your profile with the current filters. "
            "Try relaxing your budget, eligibility, or location preferences."
        )

    from engine.scoring import PARAM_LABELS

    budget = student_profile.get("budget_inr", 0)
    reasons_raw = student_profile.get("reasons", "")
    reasons = [r.strip() for r in reasons_raw.split(",") if r.strip()] if reasons_raw else []
    reasons_str = " and ".join(reasons) if reasons else "personal growth"

    top = ranked_programs[0]
    top_name = f"{top['university']} — {top['program_name']}"
    top_score = top.get("score_pct", 0)
    top_params = _top_two_params(top.get("contributions", {}))
    top_params_str = " and ".join(top_params) if top_params else "overall quality"
    top_fee = top.get("fee_inr", 0)
    top_placement = top.get("placement_pct", 0)

    lines = [
        f"Based on your ₹{budget:,} budget and goal of {reasons_str}, "
        f"we found {len(ranked_programs)} program(s) that fit your profile.",

        f"{top_name} ranks first (score {top_score}%), "
        f"driven mainly by strong {top_params_str}.",
    ]

    if top_placement:
        lines.append(
            f"It reports a {top_placement}% placement rate, "
            f"and costs ₹{top_fee:,} — within your budget."
        )

    if len(ranked_programs) > 1:
        second = ranked_programs[1]
        second_name = f"{second['university']} — {second['program_name']}"
        second_score = second.get("score_pct", 0)
        lines.append(
            f"{second_name} is a strong second choice at {second_score}%, "
            f"offering an alternative at ₹{second.get('fee_inr', 0):,}."
        )

    lines.append(
        "All programs listed are fully within your budget and eligibility — "
        "click Apply to explore further."
    )

    return " ".join(lines)


def _build_prompt_payload(
    student_profile: dict[str, Any],
    ranked_programs: list[dict[str, Any]],
    top_n: int = 3,
) -> list[dict[str, str]]:
    """Build the system + user messages for the Azure OpenAI call."""
    from engine.scoring import PARAM_LABELS

    system_msg = (
        "You are an education counselor. You are given a student profile and "
        "a pre-computed, pre-ranked shortlist with scores. Explain in 4-6 sentences "
        "why these programs suit this student, referencing their budget, goal, and "
        "the scores provided. Do not change the order. Do not mention any program not "
        "in the list. Do not invent numbers — use only the scores given."
    )

    top_progs = ranked_programs[:top_n]
    prog_summaries = []
    for p in top_progs:
        top_params = _top_two_params(p.get("contributions", {}))
        prog_summaries.append({
            "university": p.get("university"),
            "program": p.get("program_name"),
            "fee_inr": p.get("fee_inr"),
            "score_pct": p.get("score_pct"),
            "placement_pct": p.get("placement_pct"),
            "top_2_params": top_params,
            "apply_url": p.get("apply_url"),
        })

    user_payload = {
        "student_profile": {
            "budget_inr": student_profile.get("budget_inr"),
            "qualification_pct": student_profile.get("qualification_pct"),
            "level": student_profile.get("level"),
            "specialization": student_profile.get("specialization"),
            "reasons": student_profile.get("reasons"),
            "city": student_profile.get("city"),
        },
        "ranked_programs": prog_summaries,
    }

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def generate_narrative(
    student_profile: dict[str, Any],
    ranked_programs: list[dict[str, Any]],
    top_n: int = 3,
) -> str:
    """
    Generate a personalized narrative for the ranked shortlist.

    Tries Azure OpenAI if credentials are available; falls back to the
    deterministic template on any error or when creds are missing.

    Parameters
    ----------
    student_profile  : student form data dict
    ranked_programs  : already-ranked list from score_programs()
    top_n            : how many programs to include in the narrative (default 3)

    Returns
    -------
    str — narrative text (never empty, never raises)
    """
    if not config.azure_creds_available():
        logger.info("Azure creds not configured — using deterministic narrative fallback.")
        return _deterministic_fallback(student_profile, ranked_programs)

    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )

        messages = _build_prompt_payload(student_profile, ranked_programs, top_n)

        response = client.chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            temperature=0.3,
            max_tokens=400,
        )

        narrative = response.choices[0].message.content.strip()
        if not narrative:
            raise ValueError("Empty response from Azure OpenAI")
        return narrative

    except Exception as exc:
        logger.warning("Azure OpenAI call failed (%s) — using deterministic fallback.", exc)
        return _deterministic_fallback(student_profile, ranked_programs)
