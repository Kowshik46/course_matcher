# CLAUDE.md

Conventions and guardrails for working in this repo. Read this before writing
code. The full spec is in **BUILD_PLAN.md** — that file is the source of truth
for schema, scoring math, routes, and build order. This file is the *how we
work* layer on top of it.

## What this is

A local POC: a personalized course/program recommender (Indian online degrees +
certifications). A student enters a profile, a **deterministic engine** filters
and ranks a curated catalogue, and an **LLM writes only the explanation**.
Stack: Flask + SQLite (stdlib `sqlite3`) + Azure OpenAI.

## The one rule that matters most

**The LLM never filters and never ranks.** All threshold, eligibility, and
ranking logic lives in plain, unit-testable Python under `engine/`. The LLM
(`llm/narrative.py`) receives an already-decided, already-ordered result and
writes prose about it — it cannot reorder, cannot add or drop programs, cannot
invent numbers. If you ever find yourself passing raw programs to the model and
asking it to "pick the best," stop — that's the anti-pattern this project exists
to avoid.

Corollary: **the app must run end-to-end with no Azure credentials set.**
Matching works without the LLM; the narrative falls back to a deterministic
template. Never let an LLM call block or break the recommendation flow.

## Build discipline

- Follow the build sequence in BUILD_PLAN.md §12. **One milestone at a time.**
  Get it running, confirm it, then move on. Don't scaffold all seven steps at
  once.
- **Prove the engine before building any UI** (BUILD_PLAN.md §5.4). Write the
  asserts, run them, see them pass. The engine is the product; the UI is a
  window onto it.
- After each milestone, state what now works and how to verify it.

## Coding conventions

- Python 3.11+. Standard library `sqlite3` — **no ORM, no SQLAlchemy.** Queries
  stay readable and inspectable.
- Server-rendered Jinja2 templates. **Near-zero JavaScript** — only what the
  score-breakdown hover needs. No frontend framework, no build step.
- Parameterized SQL only (`?` placeholders). Never string-format values into
  queries.
- **Percent convention is 0–100 everywhere** (`min_eligibility_pct`,
  `qualification_pct`, `placement_pct`). If a form sends `0.45`, coerce to `45`
  at the boundary; store and compare as 0–100. Pick the convention once, in one
  helper, and use it everywhere.
- Keep functions small and pure in `engine/`. Filtering, weighting, and scoring
  are separate modules and must be independently testable.
- Money is `fee_inr` / `budget_inr` as plain integer rupees. No floats for money.

## Secrets & config

- All config via env (`python-dotenv`). Provide `.env.example`; never commit a
  real `.env`. Azure keys are read at call time in `llm/`, nowhere else.
- The four Azure vars (`AZURE_OPENAI_ENDPOINT`, `_API_KEY`, `_DEPLOYMENT`,
  `_API_VERSION`) are all optional at runtime — blank = use the template
  fallback.

## Seed data

- `programs_seed.json` populates the catalogue via `seed.py`. Read the
  `programs` array; respect the `_meta` block.
- **The seed numbers are synthetic placeholders.** Real provider names, but
  fabricated fees, eligibility, placement %, and scores. Never surface a claim
  like "JAIN places 78% of students" as fact anywhere in the UI or logs — these
  are test fixtures. A real build must replace them with sourced data.
- `seed.py` is idempotent: clear-and-reload, or no-op if already populated.

## Scope guardrails — do NOT add these unless asked

- No LinkedIn scraping/enrichment. Intake fields are entered manually.
- No payments, commission, or revenue tracking.
- No auth on the `/admin` routes (local POC; note the risk in the README).
- No real-data sourcing for placements/QS — that's a separate, deliberate effort.

If a change would pull in any of the above, flag it and ask before doing it.

## Definition of done (per BUILD_PLAN.md §13)

`flask run` works with no Azure creds; the worked example (masters / Finance /
Bengaluru / online / ₹3,00,000 / 45% / Job Change + Salary Hike) returns a
sensible ranked Finance shortlist with placements weighted highest, visible
apply links, and a per-parameter score breakdown; changing budget / eligibility
/ reasons visibly and traceably shifts the result; and nothing in filtering or
ranking depends on the LLM.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optionally fill in Azure vars
python seed.py              # load programs_seed.json into SQLite
flask --app app run --debug
# student form: http://127.0.0.1:5000/
# catalogue:    http://127.0.0.1:5000/admin/programs
```
