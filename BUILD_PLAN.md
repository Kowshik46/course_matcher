# Personalized Course Recommendation — POC Build Plan

> Hand this file to Claude Code as the spec. It is self-contained: schema, scoring math, prompt design, routes, file layout, and a build order. Follow it section by section.

---

## 0. What this POC must prove

A single thing: **the matching works and is explainable.** Given a student's
profile, the system filters a curated catalogue down to programs that actually
fit (budget, eligibility, location, level, field), ranks the survivors by a
transparent weighted score across 8 quality parameters, and hands the ranked
result to an LLM that *only writes the explanation*. Every filter and ranking
decision must be reproducible **without** the LLM.

Success = an engineer can change one input (budget, eligibility %, reason for
study) and watch the filtered set and the ranking order change in a way that is
fully traceable to the rules — not to a model's mood.

**Explicitly out of scope for the POC** (do not build these):
- LinkedIn scraping / enrichment (intake fields are entered manually)
- Payments, commission tracking, or the 10% revenue model
- User accounts / auth (the admin UI is unguarded — local POC only)
- Real placement/QS data sourcing (we seed plausible values by hand)

---

## 1. Stack & dependencies

- **Python 3.11+**, **Flask** (server-rendered templates, no SPA)
- **SQLite** via the stdlib `sqlite3` (no ORM — keep it inspectable)
- **Azure OpenAI** for the narrative only, called through the `openai` SDK
  (`AzureOpenAI` client)
- **Jinja2** templates (ships with Flask), vanilla CSS, near-zero JS

`requirements.txt`:
```
Flask>=3.0
openai>=1.40
python-dotenv>=1.0
```

The app must run with **no Azure credentials set** — in that case the narrative
falls back to a deterministic template (see §6). The matching never depends on
the LLM.

---

## 2. Architecture (the non-negotiable separation)

```
  Student intake (manual form)
        │
        ▼
  ┌─────────────────┐
  │  HARD FILTER     │   deterministic — drops programs that don't fit
  │  (engine/filters)│   budget, level, mode, location, eligibility, field
  └────────┬─────────┘
           ▼
  ┌─────────────────┐
  │  WEIGHTED SCORE  │   deterministic — 8 params × dynamic weights
  │  (engine/scoring)│   weights shift based on "reason for study"
  └────────┬─────────┘
           ▼  ranked list + per-program score breakdown (pure data)
  ┌─────────────────┐
  │  LLM NARRATIVE   │   explanation ONLY. Cannot re-rank, cannot invent
  │  (llm/narrative) │   programs. Falls back to a template if no creds.
  └────────┬─────────┘
           ▼
  Results page: ranked cards + apply links + score bars + narrative
```

The rule, same as the Overbooking Co-Pilot: **all threshold and ranking logic
lives in plain Python and is unit-testable. The LLM receives already-decided
results and writes prose about them.**

---

## 3. Project structure

```
course-reco-poc/
├── app.py                  # Flask app + all routes
├── config.py               # env loading (dotenv), Azure config
├── db.py                   # connection helper + init_db()
├── schema.sql              # table DDL
├── seed.py                 # loads ~20-25 sample programs
├── engine/
│   ├── __init__.py
│   ├── filters.py          # hard-constraint filtering
│   ├── weights.py          # base weights + reason-based adjustment
│   └── scoring.py          # normalize, weight, sum, sort
├── llm/
│   ├── __init__.py
│   └── narrative.py        # Azure OpenAI call + deterministic fallback
├── templates/
│   ├── base.html
│   ├── intake.html         # student form  (GET /)
│   ├── results.html        # ranked output (POST /recommend)
│   ├── admin_list.html     # program catalogue (GET /admin/programs)
│   └── admin_form.html     # add / edit a program
├── static/
│   └── css/styles.css
├── .env.example
├── requirements.txt
└── README.md
```

---

## 4. Data model (SQLite)

### `programs` — the catalogue (populated via the ingestion UI + seed)

| column              | type    | notes |
|---------------------|---------|-------|
| id                  | INTEGER PK |  |
| university          | TEXT    | e.g. "JAIN Online" |
| program_name        | TEXT    | e.g. "Online MBA — Finance" |
| level               | TEXT    | `bachelors` \| `masters` \| `certification` |
| specialization      | TEXT    | e.g. "Finance" (free text, matched case-insensitively) |
| mode                | TEXT    | `online` \| `offline` \| `hybrid` |
| fee_inr             | INTEGER | total program fee in ₹ |
| city                | TEXT    | campus city (nullable for pure-online) |
| state               | TEXT    | campus state (nullable for pure-online) |
| min_eligibility_pct | REAL    | minimum qualifying % the program accepts (0–100) |
| apply_url           | TEXT    | link the student clicks to apply |
| placement_pct       | REAL    | % of cohort placed (real signal, 0–100) |
| **8 ranking params, each 0–10:** | | |
| brand_score         | REAL    |  |
| placements_score    | REAL    |  |
| course_depth_score  | REAL    | depth of course / electives |
| faculty_score       | REAL    | teaching staff potential |
| support_score       | REAL    | student support |
| infra_score         | REAL    | infrastructure |
| accreditation_score | REAL    | approvals / accreditations |
| qs_score            | REAL    | QS ranking strength |
| approvals_text      | TEXT    | e.g. "UGC, NAAC A+, AICTE" (shown on card) |
| notes               | TEXT    | optional |
| created_at          | TEXT    | ISO timestamp |

### `leads` — log each intake (so we can replay matches)

| column            | type    | notes |
|-------------------|---------|-------|
| id                | INTEGER PK |  |
| age               | INTEGER |  |
| city              | TEXT    |  |
| state             | TEXT    |  |
| level             | TEXT    | desired level |
| specialization    | TEXT    | desired field, e.g. "Finance" |
| mode              | TEXT    | `online` \| `offline` \| `no_preference` |
| budget_inr        | INTEGER |  |
| qualification_pct | REAL    | highest qualification % (0–100) |
| reasons           | TEXT    | CSV of selected reasons (see §5.3) |
| derived_income    | INTEGER | **captured but unused in matching** for POC |
| created_at        | TEXT    | ISO timestamp |

`schema.sql` should `CREATE TABLE IF NOT EXISTS` both. `db.init_db()` runs it on
startup. `derived_income` is collected on the form as a manual optional number;
it is logged but does **not** feed filtering or scoring in the POC (budget is
the financial constraint). Leave a clear `# TODO: future use` comment.

---

## 5. The engine (deterministic — the heart of the POC)

### 5.1 Hard filter — `engine/filters.py`

A program **passes** only if ALL of these hold. Drop it otherwise.

1. **Level** matches the requested level exactly.
2. **Field**: `specialization` matches the requested field, case-insensitive
   substring either direction (so "Finance" matches "MBA Finance").
3. **Budget**: `fee_inr <= budget_inr`.
4. **Eligibility**: `min_eligibility_pct <= student.qualification_pct`
   (i.e. the program accepts someone at the student's %). In the worked
   example the student is at 45%, so only programs accepting ≤45% survive.
5. **Mode**:
   - student `online`  → program mode in {`online`, `hybrid`}
   - student `offline` → program mode in {`offline`, `hybrid`}
   - student `no_preference` → any mode
6. **Location** — only applies to **non-online** programs. If the program mode
   is `online`, location is irrelevant and always passes. Otherwise it passes
   if `program.city == student.city` OR `program.state == student.state`.

Return the surviving list plus, for transparency/debugging, a per-program
record of which rule (if any) eliminated it (useful on an admin/debug view; not
required on the student page).

### 5.2 Weighted scoring — `engine/scoring.py`

For each surviving program:

```
normalized_i = param_i / 10.0            # each of the 8 params, 0..10 → 0..1
score        = Σ ( weight_i * normalized_i )   for i in the 8 params
score_pct    = round(score * 100, 1)     # 0..100, shown to the user
```

Weights always sum to 1.0 (renormalize after any adjustment). Sort survivors by
`score` descending; ties broken by `placement_pct` desc, then `fee_inr` asc.

Return for each program: the final `score_pct` **and** the per-parameter
contribution (`weight_i * normalized_i * 100`) so the UI can draw the breakdown.

### 5.3 Dynamic weights — `engine/weights.py`

Base weights (sum = 1.00):

| parameter       | base weight |
|-----------------|-------------|
| placements      | 0.18 |
| accreditation   | 0.15 |
| brand           | 0.14 |
| qs              | 0.13 |
| course_depth    | 0.12 |
| faculty         | 0.11 |
| support         | 0.09 |
| infra           | 0.08 |

Reasons for study (multi-select) **nudge** the weights, then we renormalize to
sum 1.0. Apply every selected reason's deltas additively:

| reason            | weight deltas (before renormalize) |
|-------------------|-------------------------------------|
| Job Change        | placements +0.06, brand +0.03 |
| Salary Hike       | placements +0.06, brand +0.02 |
| Industry Shift    | course_depth +0.05, placements +0.03 |
| Move Abroad       | qs +0.07, accreditation +0.04 |
| Others            | (no change) |

This encodes the original spec note — "*as Job change & salary hike are imp,
weight placements higher*" — as explicit, inspectable math rather than asking
the model to "consider" it. Expose the final weight vector on the results page
(small print) so the ranking is auditable.

### 5.4 Acceptance test for the engine

Write `engine`-level checks (a `tests/` file or asserts in a `__main__` block):

- The worked example (Masters / Finance / Bangalore / online / ₹3,00,000 budget
  / 45% / reasons = Job Change + Salary Hike) returns a non-empty ranked list,
  and placements has the **highest** weight in the final vector.
- Dropping budget to ₹1,00,000 shrinks or empties the survivor set.
- Raising eligibility filter pressure (student at 40%) drops programs that
  require ≥45%.
- Removing all reasons returns base weights exactly.
- Running the engine twice on the same input yields identical ordering (no
  LLM, fully deterministic).

---

## 6. LLM narrative — `llm/narrative.py`

**Role:** turn the already-ranked top-N (default N=3) into a short, personalized
explanation. It must NOT re-order, NOT add programs, NOT invent facts.

**Azure config (env):** `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` (e.g. `2024-06-01`).
Use the `AzureOpenAI` client, `temperature=0.3`.

**Prompt shape** (system + user):

- *System:* "You are an education counselor. You are given a student profile and
  a pre-computed, pre-ranked shortlist with scores. Explain in 4–6 sentences why
  these programs suit this student, referencing their budget, goal, and the
  scores provided. Do not change the order. Do not mention any program not in
  the list. Do not invent numbers — use only the scores given."
- *User:* a compact JSON block with the student profile and the ranked programs
  (university, program, fee, score_pct, placement_pct, top 2 contributing
  parameters each, apply_url).

**Fallback (no creds or API error):** generate a deterministic template, e.g.
"Based on your ₹X budget and goal of {reason}, {top university} ranks first
(score Y%), driven mainly by {param a} and {param b}…" built from the same data.
The page must render identically whether the narrative came from Azure or the
fallback — never error out, never block on the LLM.

---

## 7. Routes — `app.py`

| method | path | purpose |
|--------|------|---------|
| GET    | `/`  | student intake form (`intake.html`) |
| POST   | `/recommend` | log lead → filter → score → narrative → `results.html` |
| GET    | `/admin/programs` | catalogue list w/ edit & delete (`admin_list.html`) |
| GET    | `/admin/programs/new` | blank program form (`admin_form.html`) |
| POST   | `/admin/programs` | create program |
| GET    | `/admin/programs/<id>/edit` | edit form |
| POST   | `/admin/programs/<id>` | update program |
| POST   | `/admin/programs/<id>/delete` | delete program |
| GET    | `/healthz` | returns `{"ok": true}` |

Keep request parsing tolerant (default missing numerics sensibly, coerce `%`
inputs that arrive as `0.45` or `45` to a single convention — store eligibility
and qualification as **0–100**).

---

## 8. The two UIs

### 8.1 Student flow
- **Intake (`/`)**: one clean form — age, city, state, level (radio), field
  (text), mode (radio incl. "no preference"), budget (₹), highest qualification
  %, reasons (checkboxes, multi), optional monthly income. Submit = "Find my
  programs."
- **Results (`/recommend`)**: ranked cards (rank 1 highlighted), each showing
  university + program, fee, an **Apply** button (→ `apply_url`), the
  **score breakdown** (horizontal bars, one stacked bar per program showing each
  parameter's contribution), placement %, and accreditations. Above the cards,
  the LLM narrative. Below, small print: the final weight vector used and how
  many programs were filtered out. Empty state: "No programs match yet — try a
  higher budget or broader location," never a blank page.

### 8.2 Ingestion flow (admin)
- **List (`/admin/programs`)**: table of all programs with edit/delete and a
  prominent "Add program" button.
- **Form (`/admin/programs/new` & edit)**: every column from §4, the 8 params as
  0–10 number inputs with helper labels. This is the tool you'll use to load the
  curated catalogue by hand.

---

## 9. Seed data — `seed.py`

Load ~20–25 plausible programs spanning **degrees + certifications** so filters
have something to bite on. Include at least: a few online MBA-Finance options
(JAIN Online, Amity Online, NMIMS Global, etc. — plausible fees/eligibility),
some non-Finance masters, a couple of offline programs in different
cities/states (to exercise the location filter), and several certifications
(varying fee/field). Spread the 8 param scores so ranking actually differentiates.
`seed.py` should be idempotent (clear + reload, or skip if already seeded) and
runnable via `python seed.py`.

---

## 10. Config & secrets

`.env.example`:
```
FLASK_SECRET_KEY=dev-only-change-me
DATABASE_PATH=course_reco.db
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2024-06-01
```
`config.py` loads via `python-dotenv`. The app must boot and the matching must
work with all Azure fields blank.

---

## 11. Design direction (so the UI doesn't look templated)

Subject: a credible, transparent education *advisor* — the differentiator is
that it shows its work. Spend the boldness in one place: the **score-breakdown
bars** are the signature. Everything else stays quiet and disciplined.

- **Palette:** ink `#15233B` (deep academic navy), paper `#F7F6F2` (warm off-white,
  not cream-cliché), primary/teal `#2F6F6A` (actions + score bars), credential
  gold `#C9A227` (rank-1 badge + accreditations), muted `#6B7280`, hairline
  `#E3E0D8`.
- **Type:** display **Fraunces** (headings, used sparingly), body **Inter**,
  data/scores **IBM Plex Mono** (so numbers feel like instrument readouts). Pull
  from Google Fonts.
- **Signature:** each program card carries a single horizontal stacked bar where
  the 8 weighted contributions are visible segments — the ranking is literally
  the picture. Hovering a segment shows the parameter + its contribution.
- Quality floor: responsive to mobile, visible keyboard focus, `prefers-reduced-
  motion` respected, sentence-case copy, active-voice buttons ("Find my
  programs", "Apply"). No purple EdTech gradients.

---

## 12. Build sequence (do in this order)

1. **Scaffold** — project tree, `requirements.txt`, `config.py`, `db.py`,
   `schema.sql`, `app.py` booting with `/healthz` and `init_db()`.
2. **Ingestion** — `admin_list` + `admin_form` CRUD, then `seed.py`. Verify you
   can add/edit/delete and that seed loads.
3. **Engine** — `filters.py`, `weights.py`, `scoring.py` with the §5.4 tests
   passing. No UI yet — prove it in `python -m` asserts.
4. **Student flow, no LLM** — `intake.html` → `/recommend` → `results.html`
   rendering ranked cards + breakdown from the engine only.
5. **LLM narrative** — wire `llm/narrative.py` with the fallback first, then the
   Azure path; confirm the page is identical with creds blank vs set.
6. **Design pass** — apply §11, the signature bars, responsive + a11y, empty
   states.
7. **README** — run steps, env setup, the worked-example walkthrough.

Stop after each step and confirm it runs before moving on.

---

## 13. Done criteria

- `flask run` works with **no** Azure creds; matching + ranking + fallback
  narrative all function.
- The worked example returns a sensible ranked Finance shortlist with placements
  weighted highest, visible apply links, visible per-parameter breakdown.
- Toggling budget / eligibility / reasons visibly and traceably changes the
  result.
- The catalogue is fully manageable through the ingestion UI.
- Nothing in filtering or ranking depends on the LLM.

---

## 14. Deliberately deferred (note in README as "next")

LinkedIn enrichment (OAuth, not scraping), income derivation, commission /
revenue tracking, auth on the admin UI, real placement/QS data sourcing, and the
trusted-advisor-vs-broker ranking-transparency policy. None of these block the
POC; all of them matter for a real product.
