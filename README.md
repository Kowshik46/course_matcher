# Course Advisor — Personalized Program Recommender (POC)

A Flask + SQLite proof-of-concept that matches students to Indian online
degrees and certifications using a fully deterministic engine, then uses an
LLM (Azure OpenAI) to write a plain-English explanation of the result.

**The matching never depends on the LLM.** All filtering and ranking is in
`engine/`; the LLM only writes prose. The app boots and produces ranked
results with zero Azure credentials.

---

## Run steps

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (Azure vars are optional)
cp .env.example .env
# Edit .env and set FLASK_SECRET_KEY to a random string.
# Optionally fill in the four AZURE_OPENAI_* vars for LLM narratives.

# 4. Seed the catalogue
python seed.py
# Output: "Seeded 25 programs into the database."

# 5. Run the dev server
flask --app app run --debug

# Student intake form:  http://127.0.0.1:5000/
# Admin catalogue:      http://127.0.0.1:5000/admin/programs
# Health check:         http://127.0.0.1:5000/healthz
```

---

## Environment variables (`.env.example`)

| Variable                  | Required | Notes |
|---------------------------|----------|-------|
| `FLASK_SECRET_KEY`        | Yes      | Any random string for session signing |
| `DATABASE_PATH`           | No       | Defaults to `course_reco.db` in cwd |
| `AZURE_OPENAI_ENDPOINT`   | No       | Leave blank — deterministic fallback is used |
| `AZURE_OPENAI_API_KEY`    | No       | Leave blank |
| `AZURE_OPENAI_DEPLOYMENT` | No       | Leave blank |
| `AZURE_OPENAI_API_VERSION`| No       | Defaults to `2024-06-01` |

---

## Running the tests

```bash
pip install pytest          # if not already installed
pytest tests/test_engine.py -v
```

All five acceptance tests from the build spec must pass.

---

## Worked-example walkthrough

**Input:** Masters / Finance / Bengaluru / Online / ₹3,00,000 / 45% /
reasons: Job Change + Salary Hike

**Step 1 — Hard filter** (`engine/filters.py`) applies six rules:

1. Level = `masters` — drops bachelors and certifications
2. Specialization contains "finance" — drops Marketing, HR, Data Science, etc.
3. Fee ≤ ₹3,00,000 — drops SIBM (₹23.6L), Christ (₹8L), ICFAI (₹13L)
4. `min_eligibility_pct` ≤ 45 — **drops NMIMS** (requires 50%; demonstrates filter doing real work)
5. Mode = `online` → program mode in {online, hybrid} — drops offline programs
6. Location (only for non-online) — online programs always pass

**Survivors:** JAIN Online, Amity University Online, Manipal University
Jaipur (Online), Chandigarh University Online, LPU Online, DY Patil
University (Online)

**Step 2 — Dynamic weights** (`engine/weights.py`) with Job Change + Salary Hike:

- Base placements weight: 0.18
- Job Change adds +0.06 to placements, +0.03 to brand
- Salary Hike adds +0.06 to placements, +0.02 to brand
- After adjustments: placements = 0.30 (raw), brand = 0.19 (raw)
- Renormalized → placements has the **highest** weight (~26–28%)

**Step 3 — Scoring** (`engine/scoring.py`) calculates
`score_pct = Σ(weight_i × param_i/10) × 100` for each survivor and sorts
descending by score, then placement_pct, then fee_inr ascending.

**Expected ranking:** JAIN Online or Amity first (high placements and brand
scores), Manipal second/third, Chandigarh / LPU / DY Patil lower (lower
quality signals).

**Verify the weights shift:** Changing reasons to "Move Abroad" boosts `qs`
and `accreditation` instead, visibly reordering the cards. Removing all
reasons returns exact base weights (visible in the weights footer on the
results page).

---

## Synthetic data warning

All fees, eligibility thresholds, placement percentages, and quality scores
in `programs_seed.json` are **fabricated placeholders** for engine testing.
University and provider names are real and public, but the numbers are not
verified. Do not show these figures to real students, publish them, or treat
them as factual. Replace with sourced, verified values before any non-POC
use. This warning also appears in the site footer on every page.

---

## Deferred items (next steps)

The following are deliberately out of scope for this POC:

- **LinkedIn enrichment** — OAuth-based profile enrichment, not scraping.
  Intake fields are currently entered manually.
- **Income derivation** — `derived_income` is captured on the form and
  logged to the `leads` table but is not used in filtering or scoring.
  Marked `# TODO: future use` in the code.
- **Auth on admin routes** — `/admin/programs` is unguarded (local POC
  only). A real deployment must add authentication.
- **Real placement/QS data sourcing** — a deliberate, separate effort
  requiring partnerships or verified scraping.
- **Commission / revenue tracking** — out of scope for the matching POC.
- **Trusted-advisor ranking-transparency policy** — how to communicate
  ranking methodology to students in a production context.
