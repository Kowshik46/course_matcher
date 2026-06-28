# How the Matching Algorithm Works

There are two sequential stages — both fully deterministic, no LLM involved.

---

## Stage 1 — Hard Filter (`engine/filters.py`)

Every program in the catalogue is tested against **6 binary rules**. A program must pass **all 6** or it is dropped entirely.

| Rule | Logic |
|------|-------|
| **Level** | Program level must exactly match what the student wants (masters / bachelors / certification) |
| **Field** | Case-insensitive substring match in either direction — "Finance" matches "MBA Finance" and vice versa |
| **Budget** | `program.fee_inr <= student.budget_inr` |
| **Eligibility** | `program.min_eligibility_pct <= student.qualification_pct` — if you scored 45%, programs that require 50%+ are dropped |
| **Mode** | Online student → only online/hybrid programs pass. Offline student → only offline/hybrid. No preference → all pass |
| **Location** | Only checked for non-online programs. Must match city OR state. Pure-online programs always pass this rule |

The output is a **survivor list** — programs that cleared every rule.

---

## Stage 2 — Weighted Scoring (`engine/weights.py` + `engine/scoring.py`)

Each surviving program has **8 quality scores** (each rated 0–10 by whoever curates the catalogue):

```
brand, placements, course_depth, faculty, support, infra, accreditation, qs
```

### Step 1 — Compute weights from reasons

Base weights (always sum to 1.0):

| Parameter | Base Weight |
|-----------|-------------|
| placements | 0.18 |
| accreditation | 0.15 |
| brand | 0.14 |
| qs | 0.13 |
| course_depth | 0.12 |
| faculty | 0.11 |
| support | 0.09 |
| infra | 0.08 |

The student's selected reasons **nudge** these before scoring:

| Reason | Delta |
|--------|-------|
| Job Change | placements +0.06, brand +0.03 |
| Salary Hike | placements +0.06, brand +0.02 |
| Industry Shift | course_depth +0.05, placements +0.03 |
| Move Abroad | qs +0.07, accreditation +0.04 |

Deltas are applied additively, then the whole vector is **renormalized** to sum back to 1.0. Selecting "Job Change + Salary Hike" pushes placements from 0.18 → 0.30 (before renorm), making it the dominant factor.

### Step 2 — Score each program

```
score = Σ ( weight_i × (param_i / 10) )   for all 8 params
```

Each param is divided by 10 to normalize it to 0–1, multiplied by its weight, then summed. Result is multiplied by 100 to give a **0–100 score**.

### Step 3 — Sort

Programs sorted by score descending. Ties broken by `placement_pct` descending, then `fee_inr` ascending.

---

## Worked Example

**Student:** Masters / Finance / online / ₹3,00,000 budget / 45% qualification / Job Change + Salary Hike

**After hard filter:** 6 programs survive
- NMIMS dropped — requires 50% minimum (student has 45%)
- All offline programs dropped — fees exceed ₹3L budget

**Weights after reasons:** placements rises to ~0.30 (highest of all 8), everything else shrinks proportionally after renormalization

**Result:** Programs ranked by the new weight vector — Amity ranks #1 because it scores well on both placements and course_depth, which carry the most combined weight for this reason combination

---

## The Key Property

Change any single input — drop budget to ₹1L, remove Job Change, raise the eligibility bar — and you can trace exactly which rule or weight shift caused the result to change. Every filter decision and every ranking number is inspectable plain Python. Nothing is a black box.
