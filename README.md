# Lab Mind — Technical Documentation

> **Complete guide to the backend, frontend, and deployment of Lab Mind**

---

## Quick Start

- **Backend**: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
- **Frontend**: `cd frontend && npm install && npm run dev`
- **API**: http://localhost:8000
- **UI**: http://localhost:5173

---

## Table of Contents

1. [What it does](#1-what-it-does)
2. [Demo flow](#2-demo-flow)
3. [Tech stack](#3-tech-stack)
4. [Project structure](#4-project-structure)
5. [Quickstart (Windows · macOS · Linux)](#5-quickstart-windows--macos--linux)
6. [Environment variables](#6-environment-variables)
7. [Backend deep dive](#7-backend-deep-dive)
8. [Frontend deep dive](#8-frontend-deep-dive)
9. [API reference](#9-api-reference)
10. [Data contracts (schemas)](#10-data-contracts-schemas)
11. [Reliability & fallback strategy](#11-reliability--fallback-strategy)
12. [Literature QC algorithm](#12-literature-qc-algorithm)
13. [Experiment plan generation algorithm](#13-experiment-plan-generation-algorithm)
14. [Learning loop (stretch goal)](#14-learning-loop-stretch-goal)
15. [Design system](#15-design-system)
16. [Quality bar & known limits](#16-quality-bar--known-limits)
17. [Deployment (Render + Netlify)](#17-deployment-render--netlify)
18. [Troubleshooting](#18-troubleshooting)
19. [Roadmap](#19-roadmap)
20. [Credits](#20-credits)

---

## 1) What it does

The challenge: turning a scientific question into a runnable experiment normally takes weeks of manual work — designing the protocol, sourcing materials, estimating costs, staffing the team. **Lab Mind** compresses that to seconds.

It is a focused, end-to-end application with **three stages**:

| # | Stage | Output |
|---|-------|--------|
| 1 | **Input** | A natural-language scientific hypothesis (with a specific intervention, measurable outcome, and mechanism). |
| 2 | **Literature QC** | A novelty signal (`not_found` · `similar_exists` · `exact_match`) plus 1–3 cited references — a "plagiarism check, but for science." |
| 3 | **Experiment Plan** | A complete operational plan: protocol, reagents with catalog numbers, budget breakdown, phased timeline, and validation criteria — exportable to PDF. |

A **scientist-review** loop captures expert corrections and feeds them back into future plans (the "compounding-learning" stretch goal).

---

## 2) Demo flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. INPUT   →   Type or click a sample hypothesis (Diagnostics / Gut Health / │
│                Cell Biology / Climate). Min 20 characters.                   │
│                                                                              │
│ 2. LIT QC  →   Hits Tavily + OpenAlex (parallel). Falls back to Semantic     │
│                Scholar if thin. Heuristic + LLM reconcile a novelty signal.  │
│                Pill colour reflects severity. References cite their source.  │
│                                                                              │
│ 3. PLAN    →   Groq generates a structured JSON plan; FastAPI normalises it  │
│                through Pydantic. UI renders 5 tabs: Protocol · Reagents ·    │
│                Budget (donut chart) · Timeline (gantt) · Validation. Export  │
│                to PDF, download reagents CSV.                                │
│                                                                              │
│ 4. REVIEW  →   Slide-over panel with star ratings + free-text correction per │
│                section. POST /api/save-feedback persists it.                 │
│                The next plan for the same experiment_type silently applies   │
│                the prior corrections.                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Sample hypotheses bundled in the UI (from the challenge brief):

- 🩸 **Diagnostics** — paper-based electrochemical biosensor for CRP detection.
- 🧬 **Gut Health** — *L. rhamnosus* GG and intestinal-permeability reduction in C57BL/6 mice.
- 🧫 **Cell Biology** — trehalose vs DMSO cryoprotectant for HeLa cells.
- 🌱 **Climate** — *Sporomusa ovata* CO₂-fixation in a bioelectrochemical system.

---

## 3) Tech stack

### Backend
| Layer | Choice | Why |
|-------|--------|-----|
| HTTP framework | **FastAPI** (`>=0.109`) | Async, auto-docs, great for typed JSON contracts. |
| ASGI server | **uvicorn** | Standard, with hot reload in dev. |
| Schema validation | **Pydantic v2** | Strict typing on every API boundary. |
| LLM provider | **Groq** | Free-tier, sub-second 70B tokens, OpenAI-compatible client. |
| Web search | **Tavily** | Academic-domain grounded search with paid free tier. |
| Academic metadata | **OpenAlex** (no key) + **Semantic Scholar** (key optional) | Clean author/year/DOI structured data. |
| Async HTTP | **httpx** | Parallel external calls; no event-loop blocking. |
| Env mgmt | **python-dotenv** | Reads local `.env`. |

### Frontend
| Layer | Choice | Why |
|-------|--------|-----|
| Framework | **React 18** + **Vite 5** | Fast dev server, modern tooling. |
| Styling | **Tailwind CSS 3.4** + custom design tokens | Premium look without a heavy component lib. |
| Charts | **Chart.js** (CDN-loaded) | Donut chart for budget, gantt-like for timeline. |
| State | Plain `useState` (intentionally) | One-page app with a finite state machine. |
| HTTP | `fetch` | No client lib needed. |
| Print | Custom `@media print` stylesheet + `data-print-all` toggle | One-click "Export PDF" via `window.print()`. |

---

## 4) Project structure

```
ai-scientist-main - Copy/
├── README.md                       ← this file
├── challenge.txt                   ← original challenge brief
│
├── backend/
│   ├── main.py                     ← FastAPI app: 4 endpoints + Pydantic models +
│   │                                  fallback chain + demo dispatcher + skeleton plan
│   ├── literature.py               ← Lit-QC pipeline: keywords → Tavily/OpenAlex/SS →
│   │                                  novelty signal (heuristic + LLM, two-sided reconciliation)
│   ├── prompts.py                  ← SYSTEM_PROMPT (strict JSON schema) +
│   │                                  build_prompt_with_feedback (learning loop)
│   ├── feedback_store.json         ← Persisted scientist corrections (plain JSON)
│   ├── requirements.txt
│   ├── .env.example                ← GROQ_API_KEY + TAVILY_API_KEY
│   └── .env                        ← (git-ignored, your real secrets)
│
└── frontend/
    ├── index.html                  ← shell + Inter / JetBrains Mono fonts + Chart.js CDN
    ├── package.json                ← React 18, Vite 5, Tailwind 3.4
    ├── tailwind.config.js          ← Custom design tokens (ink / accent / signal palettes)
    ├── postcss.config.js
    ├── vite.config.js              ← dev server + /api proxy
    ├── .env.example                ← VITE_API_BASE_URL
    └── src/
        ├── main.jsx                ← React root
        ├── App.jsx                 ← state machine: idle → qc_running → qc_done →
        │                              generating → done; renders header, stepper, columns
        ├── index.css               ← design system: btn / card / pill / stepper /
        │                              input / table / tab / surface / print stylesheet
        └── components/
            ├── HypothesisInput.jsx ← textarea + 4 sample-hypothesis cards + char counter
            ├── LiteratureQC.jsx    ← signal pill + explanation + ref cards w/ source tags
            ├── ExperimentPlan.jsx  ← KPI summary header + 5 tabs + slide-over review +
            │                          demo-mode banner + print + feedback toast
            ├── ProtocolCard.jsx    ← step list with safety + duration + cited source
            ├── ReagentsTable.jsx   ← sortable table + CSV export
            ├── BudgetChart.jsx     ← donut chart + breakdown legend
            ├── TimelineChart.jsx   ← horizontal gantt-style chart
            ├── ValidationCard.jsx  ← 7 KPIs (metric, threshold, control, test, n, fail, std)
            └── ScientistReview.jsx ← slide-over panel: 5 sections × (5-star + textarea)
```

---

## 5) Quickstart (Windows · macOS · Linux)

> Prereqs: **Python 3.10+**, **Node 18+**, a free Groq key, and a free Tavily key.

### Backend

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with your real GROQ_API_KEY and TAVILY_API_KEY
python main.py
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real GROQ_API_KEY and TAVILY_API_KEY
python main.py
```

Backend listens on **http://localhost:8000**. Health check: `GET /api/health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend opens on **http://localhost:5173** (or the next free port). Vite proxies `/api/*` to `http://localhost:8000` in dev.

For production:

```bash
npm run build      # outputs dist/
npm run preview    # serves dist/ locally for QA
```

---

## 6) Environment variables

### `backend/.env`

| Variable | Required | Purpose | Default |
|----------|----------|---------|---------|
| `GROQ_API_KEY` | **Yes** | LLM calls. | — |
| `TAVILY_API_KEY` | Yes (for best lit QC) | Academic web search. | — |
| `GROQ_MODEL` | No | Override the primary model. | `llama-3.3-70b-versatile` |
| `GROQ_FALLBACK_MODELS` | No | Comma-separated fallback chain. | See [§11](#11-reliability--fallback-strategy) |
| `OPENALEX_MAILTO` | No | Be polite to OpenAlex. | unset |
| `SEMANTIC_SCHOLAR_API_KEY` | No | Higher rate limit. | unset |
| `PORT` | No | Backend port. (Render injects this automatically.) | `8000` |
| `ENV` | No | `production` disables hot-reload by default. Set to `production` on Render. | `development` |
| `RELOAD` | No | `1` to force hot-reload, `0` to force-disable. | `1` in dev, `0` in prod |
| `CORS_ALLOW_ORIGINS` | No | Comma-separated allowlist for CORS. Set to your Netlify URL in production. | `*` |
| `KEEP_ALIVE_ENABLED` | No | `0` to disable the self-ping anti-sleep loop. | `1` |
| `KEEP_ALIVE_INTERVAL_SECONDS` | No | How often the backend pings itself. Clamped to `[60, 840]`. | `600` (10 min) |
| `KEEP_ALIVE_URL` | No | Override the URL the keep-alive loop pings. Defaults to `RENDER_EXTERNAL_URL/api/health`. | unset |

### `frontend/.env`

| Variable | Purpose | Default |
|----------|---------|---------|
| `VITE_API_BASE_URL` | Override backend base URL. | `http://localhost:8000` |

---

## 7) Backend deep dive

### `backend/main.py`

The FastAPI app, top to bottom:

1. **Imports & config** — loads `.env`, sets up logging, instantiates `Groq` client.
2. **Model fallback chain** (`PRIMARY_MODEL` + `FALLBACK_MODELS`) — see [§11](#11-reliability--fallback-strategy).
3. **`_groq_chat_with_fallback()`** — the single entry point for every Groq call. Walks the chain on retryable errors (429 rate-limit, 413 payload-too-large, 400 `json_validate_failed`, 400 `model_decommissioned`, 5xx). Returns `(text, model_used)`.
4. **CORS middleware** — `allow_origins=["*"]` with `allow_credentials=False` (per CORS spec).
5. **Pydantic models** — `HypothesisInput`, `ReferencePaper`, `LiteratureQCResponse`, `ProtocolStep`, `Reagent`, `BudgetBreakdown`, `Budget`, `TimelinePhase`, `Validation`, `ExperimentPlanResponse`, `FeedbackCorrection`, `SaveFeedbackInput`, `SaveFeedbackResponse`, `GeneratePlanInput`.
6. **Coercion helpers** — `_coerce_float()`, `_coerce_int()`, `_coerce_str()`, `_coerce_str_list()`. LLMs frequently emit `"100 mg"` or `"$1,200"` instead of numbers; we strip noise rather than crashing the response.
7. **`_sanitise_json_text()`** — strips ` ```json ` fences and isolates the outermost `{ … }` block when models add prose around the JSON.
8. **Demo + skeleton plans** — see [§11](#11-reliability--fallback-strategy):
    - `_demo_cryopreservation_plan()`, `_demo_crispr_plan()`, `_demo_microbiome_plan()` — three high-quality cached templates.
    - `_is_compute_or_ml_hypothesis(text)` — keyword detector for ML / signal-processing / software hypotheses.
    - `_build_skeleton_plan_from_hypothesis(h)` — synthesizes a topic-aware skeleton (compute branch vs wet-lab branch) directly from the hypothesis text when no template fits.
    - `get_demo_plan_response(h)` — the dispatcher. ML/compute → skeleton; CRISPR/microbiome/cryo → cached template; everything else → skeleton. **Never** returns a wet-lab plan for a non-wet-lab hypothesis (this was the "WTF" bug fix).
9. **Plan assembly helpers** — `_build_protocol`, `_build_reagents`, `_build_budget`, `_build_timeline`, `_build_validation`, `_assemble_plan`.
    - `_build_budget()` reconciles `total_usd` with the `breakdown` sum: if breakdown sums to 0 (8B-fallback bug) but total > 0, it synthesises a sensible breakdown from the reagent line items + a 60/30/10 split of the remainder. If `total_usd` and the breakdown sum diverge by >5%, it trusts the breakdown sum.
    - `_build_timeline()` clamps `week >= 1` so we never display "Week 0".
    - `_build_validation()` tolerates older drifted keys (`metric` → `primary_metric`, `threshold` → `success_threshold`).
10. **Routes** (see [§9](#9-api-reference)).
11. **Startup** — `uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)`.

### `backend/literature.py`

Async pipeline. **No external keys other than Groq + Tavily are required** — OpenAlex and Semantic Scholar work key-less.

```
hypothesis
    │
    ▼
extract_keywords()                   ← Groq, with the same fallback chain;
                                       falls back to a stop-word-aware heuristic
    │
    ▼
parallel { Tavily, OpenAlex }        ← asyncio.gather, 12-15s timeouts each
    │
    ▼
merge + dedupe by title              ← OpenAlex first (best metadata)
    │
    ▼
if < 3 papers → Semantic Scholar     ← top-up
    │
    ▼
if 0 papers   → generate_demo_papers ← topic-bucketed cached examples (last resort)
    │
    ▼
determine_novelty_signal()
    ├── _heuristic_novelty_signal()  ← Jaccard similarity + domain-token overlap +
    │                                  substring fallback for fragmented terms
    └── LLM verdict (Groq, JSON mode, with fallback chain)
    │
    ▼
two-sided reconciliation             ← upgrades not_found→similar_exists when
                                       heuristic finds real overlap; downgrades
                                       similar_exists→not_found when overlap is null
    │
    ▼
{ signal, explanation, references[≤3] }
```

Key heuristics in `literature.py`:

- **`_normalize_token`** — cheap stem so `cells` matches `cell`, `studies` matches `study`, but keeps `rhamnosus` / `hypothesis` / `dmso` intact.
- **`_GENERIC_TERMS`** — generic lab-noise terms (`study`, `effect`, `result`, `novel`, `least`, `performance`, …) excluded from "topical" overlap to avoid spurious `similar_exists` results.
- **`_substring_domain_overlap`** — handles tokens that get fragmented by `\w+` regex (e.g. `post-thaw`, `C57BL/6`, `TGF-β`).
- **Tuned thresholds** — `similar_exists` triggers when Jaccard ≥ 0.10 OR ≥ 2 domain hits OR domain hit ratio ≥ 0.15 (high-precision academic search APIs rarely return junk).

### `backend/prompts.py`

- **`SYSTEM_PROMPT`** — a hard, schema-binding prompt. Exact required JSON shape, "real catalog numbers from Sigma/Thermo/ATCC/etc.", "non-round market prices", "specific concentrations / temperatures / incubation times", "≥4-week timeline for any wet-lab experiment", "sum of breakdown ≈ total_usd", "validation MUST include all 7 keys".
- **`_select_relevant_feedback(hypothesis, feedback_list, max_examples=3)`** — scores prior feedback entries by experiment-type token overlap with the current hypothesis. Picks up to 3 best matches; falls back to most recent if no overlap.
- **`build_prompt_with_feedback()`** — composes the user prompt. When relevant feedback exists, injects an `EXPERT FEEDBACK FROM PRIOR PLANS — apply these corrections silently` block listing each prior correction tagged by section + rating.

### `backend/feedback_store.json`

A list of `{ hypothesis, experiment_type, corrections }` entries. Each `corrections` is keyed by section (`protocol` / `reagents` / `budget` / `timeline` / `validation`) and contains `{ rating: 1-5, correction: "…" }`.

---

## 8) Frontend deep dive

### State machine — `App.jsx`

```
idle ──[submit hypothesis]──▶ qc_running ──[QC ok]──▶ qc_done
                                  │                       │
                                  └──[QC error]──▶ idle ◀──┘
                                                          │
                                  ┌──[generate plan]◀─────┘
                                  ▼
                              generating ──[plan ok]──▶ done
                                  │
                                  └──[plan error]──▶ qc_done
```

Every state transition is `useState`-driven; there's no Redux / Zustand / context to learn. An auto-dismissing **error toast** surfaces any backend error for ~6s. **`Start over`** resets everything.

### Stage stepper

A 3-step `<ol>` (`Hypothesis → Literature QC → Experiment Plan`). Stage circles flip between `upcoming · active · done` (with a `✓`). The rail between steps fills as progress advances.

### `HypothesisInput.jsx`

- Textarea (min 20 chars) with live character counter.
- 4 colour-tagged sample cards (Diagnostics, Gut Health, Cell Biology, Climate) — clicking populates the textarea.
- Submit button enabled only when ≥ 20 chars and not loading.

### `LiteratureQC.jsx`

- A signal panel coloured by tone (`success` for `not_found`, `warn` for `similar_exists`, `danger` for `exact_match`) with icon, label, summary, and the LLM/heuristic explanation.
- Reference cards. Each card carries a `via Tavily` / `via OpenAlex` / `via Semantic Scholar` / `Curated example` source pill and links out to the DOI / URL.
- "Generate experiment plan →" CTA at the bottom.

### `ExperimentPlan.jsx`

- **KPI summary header** — 4 chips: Steps · Reagents · Budget total · Weeks.
- **Demo-mode banner** — appears when `budget.currency_note` starts with "DEMO MODE", explaining the cached fallback.
- **5 tabs**: Protocol · Reagents · Budget · Timeline · Validation. Each tab is a focused view with the right component.
- **Expert review** — opens a right-edge slide-over `<ScientistReview>` (5 sections × 5-star + textarea). On submit, POSTs to `/api/save-feedback` and shows a success toast.
- **Print** — sets `data-print-all` on the `<body>` to reveal hidden tabs at print time, calls `window.print()`. The print stylesheet inverts the layout for an A4 PDF.

### Component highlights

- `ProtocolCard` — step number, title, full description, duration pill, safety note (if any), cited source.
- `ReagentsTable` — sortable table; "Download CSV" exports a clean `name,quantity,unit,concentration,supplier,catalog_number,unit_price_usd,total_cost_usd` file.
- `BudgetChart` — Chart.js donut + breakdown legend + total in the centre.
- `TimelineChart` — horizontal gantt-style bars per phase, week-numbered axis, dependency arrows.
- `ValidationCard` — 7 KPIs in a 2-column grid: primary metric, threshold, control condition, statistical test, sample size, failure criteria, reporting standard.
- `ScientistReview` — sticky header with section name, 5-star rating control, 4-row textarea per section, single "Save feedback" CTA.

### Design system — `tailwind.config.js` + `src/index.css`

Custom token palettes:

| Palette | Use |
|---------|-----|
| `ink-{50…900}` | Brand ink navy — text, dark surfaces. |
| `paper` `#fbfbfa` | Page background, warm white. |
| `accent-{50…900}` | Calm clinical blue — primary actions and links. |
| `success / warn / danger` | Semantic signal palette for QC pills, toasts, banners. |
| Standard `slate / blue / emerald / amber / rose / red` | Sample-card accents, charts. |

Custom shadows (`card`, `card-hover`, `lift`, `inset-soft`), border radius (`xl2 = 14px`), keyframes (`fade-in`, `pulse-dot`), and 30+ component primitives (`btn-primary`, `btn-secondary`, `btn-ghost`, `card`, `surface`, `pill-*`, `stepper`, `tabs`, `textarea`, `input`, `table`, `toast`, `skeleton`, …).

Print stylesheet (`@media print`) hides tabs, reveals all panels, drops the slide-over, and rebalances spacing for A4.

---

## 9) API reference

Base URL: `http://localhost:8000` (override with `VITE_API_BASE_URL`).

### `GET /api/health`
```json
{ "status": "ok", "model": "llama-3.3-70b-versatile" }
```

### `POST /api/literature-qc`
**Request:**
```json
{ "hypothesis": "Replacing sucrose with trehalose as a cryoprotectant…" }
```
**Response — `LiteratureQCResponse`:**
```json
{
  "signal": "similar_exists",
  "explanation": "Retrieved papers share core topic terms with the hypothesis (related prior work).",
  "references": [
    {
      "title": "Trehalose vs DMSO cryoprotection of mammalian cell lines",
      "authors": "Chen, L., Kawakami, S., Kuroda, K.",
      "year": 2022,
      "url": "https://doi.org/10.1016/j.cryobiol.2022.01.005",
      "source": "openalex"
    }
  ]
}
```
**Errors:** `400` (hypothesis < 20 chars), `502` (every literature source failed), `500` (unexpected).

### `POST /api/generate-plan`
**Request:**
```json
{
  "hypothesis": "…",
  "feedback_context": []   // optional list of prior feedback entries
}
```
**Response — `ExperimentPlanResponse`:** see [§10](#10-data-contracts-schemas).
**Errors:** `400` (hypothesis < 20 chars), `502` (LLM hard error not retryable), `500` (unexpected). When every model is rate-limited / decommissioned / 5xx, the server returns the topic-matched demo or skeleton plan with `200`, and `budget.currency_note` is prefixed `DEMO MODE — ...` so the UI can render the warning banner.

### `POST /api/save-feedback`
**Request:**
```json
{
  "hypothesis": "…",
  "experiment_type": "trehalose cryopreservation",
  "corrections": {
    "protocol":   { "rating": 4, "correction": "Add a Western blot validation step." },
    "reagents":   { "rating": 5, "correction": "" },
    "budget":     { "rating": 3, "correction": "FACS billed per hour." },
    "timeline":   { "rating": 4, "correction": "" },
    "validation": { "rating": 5, "correction": "" }
  }
}
```
**Response:** `{ "saved": true }`. Persisted to `backend/feedback_store.json`.

---

## 10) Data contracts (schemas)

```jsonc
// ExperimentPlanResponse
{
  "protocol": [
    { "step": 1, "title": "...", "description": "...", "duration": "2 days",
      "safety_note": "BSL-2: ...", "source": "Nature Protocols: ..." }
  ],
  "reagents": [
    { "name": "DMEM, high glucose", "quantity": 500, "unit": "mL",
      "concentration": "1×", "supplier": "Thermo Fisher",
      "catalog_number": "11965118", "unit_price_usd": 42.50,
      "total_cost_usd": 85.00, "notes": "Store at 4 °C" }
  ],
  "budget": {
    "total_usd": 4780.00,
    "currency_note": "All prices in USD, illustrative current-year estimate",
    "breakdown": [
      { "category": "Reagents & Consumables", "amount_usd": 1578.00 },
      { "category": "Equipment & Rental",     "amount_usd": 900.00  },
      { "category": "Cell Lines / Biological Materials", "amount_usd": 525.00 },
      { "category": "Labour (estimated)",     "amount_usd": 1343.00 },
      { "category": "Contingency (10%)",      "amount_usd": 434.00  }
    ]
  },
  "timeline": [
    { "week": 1, "phase": "Setup",
      "tasks": ["Order reagents", "Validate ATCC HeLa thaw"],
      "milestone": "Materials in lab and cells expanding",
      "depends_on": [] }
  ],
  "validation": {
    "primary_metric":      "Post-thaw viability (% viable cells at 24 h)",
    "success_threshold":   "Trehalose group ≥15 pp higher viability vs DMSO (p<0.05)",
    "control_condition":   "Standard 10% DMSO freezing medium",
    "statistical_test":    "Two-sided Student's t-test on biological replicates",
    "sample_size":         "n=6 per condition (power 0.8, effect size 1.0)",
    "failure_criteria":    "Trehalose viability ≤ control + 5 pp",
    "reporting_standard":  "ISO 20391-1 cell counting"
  }
}
```

All numeric fields are coerced via `_coerce_float` / `_coerce_int` so that LLM outputs like `"100 mg"`, `"$1,200"`, `"~45.00"`, or even `null` never crash the response.

---

## 11) Reliability & fallback strategy

This is the section the hackathon judging cares about most: **the demo never crashes.**

### Layer 1 — Groq model fallback chain

`main.py` and `literature.py` share one chain (configurable via `GROQ_FALLBACK_MODELS`). Verified active against `https://api.groq.com/openai/v1/models` on **2026-04-26**.

```
llama-3.3-70b-versatile             ← primary (highest quality)
  → openai/gpt-oss-120b             ← OpenAI 120B open-weight
  → meta-llama/llama-4-scout-17b    ← Llama 4 Scout 17B
  → qwen/qwen3-32b                  ← strong on structured output
  → openai/gpt-oss-20b              ← OpenAI 20B
  → groq/compound                   ← Groq routing model
  → llama-3.1-8b-instant            ← last resort, fastest
```

`_groq_chat_with_fallback()` walks this chain on **any retryable error**:

- `429` (rate-limit / TPD / RPD / TPM / quota)
- `413` (payload too large)
- `400 json_validate_failed`
- `400 model_decommissioned` — the chain "self-heals" if Groq retires a model
- `5xx` server errors

Non-retryable errors short-circuit and surface as a `502` to the client.

### Layer 2 — Topic-matched demo dispatcher

When **every** model fails, `get_demo_plan_response(hypothesis)` returns a topically aligned cached plan:

- ML/signal-processing/software hypothesis (deepfake, ASVspoof, transformer, F1-score, dataset, …) → `_build_skeleton_plan_from_hypothesis()` **compute branch** (GPU-hours, baseline + ablation protocol, no wet-lab reagents).
- CRISPR / Cas9 / sgRNA / gene knockout → `_demo_crispr_plan()`.
- Microbiome / probiotic / *Lactobacillus* / intestinal-permeability → `_demo_microbiome_plan()`.
- Cryoprotectant / trehalose / post-thaw / vitrification → `_demo_cryopreservation_plan()`.
- Anything else → wet-lab skeleton derived from hypothesis text.

Every demo plan tags `budget.currency_note` with `DEMO MODE — …`, which the UI renders as a yellow banner: *"Showing a cached demo plan. Live plan generation hit a provider limit — click Start over in a few minutes to retry."*

> **Why this matters:** the prior version always defaulted to the cryopreservation cache, so a deepfake hypothesis could come back with HeLa cells and DMSO reagents. The new dispatcher **never** shows wet-lab reagents for a compute hypothesis.

### Layer 3 — Plan assembly tolerance

- **Budget reconciliation** — if breakdown sums to 0 but `total_usd > 0` (the 8B model occasionally emits zeros), `_build_budget()` synthesises a breakdown from reagent line items + a 60/30/10 split of the remainder. If `total_usd` and the breakdown sum diverge by >5%, the breakdown sum wins.
- **Timeline clamp** — `week` is forced to `≥ 1` so we never render "Week 0".
- **Validation tolerance** — older keys (`metric` / `threshold`) are accepted as fallbacks for `primary_metric` / `success_threshold`.
- **JSON repair** — if `json.loads()` on the first response fails, we ask the model again with a tight "you repair invalid JSON" system message before falling through to the demo.

### Layer 4 — Literature QC fallback

OpenAlex and Tavily run in parallel (`asyncio.gather`). If both return < 3 papers, Semantic Scholar is queried as a top-up. If everything fails, `generate_demo_papers()` returns 1–2 topic-bucketed curated examples so the UI still shows a result.

---

## 12) Literature QC algorithm

`run_literature_qc(hypothesis)`:

1. **Keyword extraction** — `extract_keywords()` asks Groq for 4–6 specific scientific terms (organism, chemical, assay, outcome). On any failure, `_fallback_keywords()` runs a stop-word-aware regex pass.
2. **Parallel academic search** — Tavily + OpenAlex via `asyncio.gather`. Tavily is scoped to 24 academic domains (`arxiv.org`, `pubmed.ncbi.nlm.nih.gov`, `nature.com`, `science.org`, `protocols.io`, …). 12–15s per source.
3. **Merge + dedupe** by lowercased title; OpenAlex preferred for cleaner author/year.
4. **Top-up** with Semantic Scholar when `< 3` papers; demo-papers fallback only when `0`.
5. **Heuristic scoring** — `_heuristic_novelty_signal()`:
    - Jaccard similarity over normalized 3+-char tokens (excluding stop-words and generic noise).
    - Domain-term overlap: count topical (non-generic) tokens shared between hypothesis and each title; substring fallback catches `post-thaw`, `C57BL/6`, etc.
    - Thresholds: `exact_match` if Jaccard ≥ 0.5 or domain ratio ≥ 0.55; `similar_exists` if Jaccard ≥ 0.10, ≥ 2 domain hits, or ratio ≥ 0.15; else `not_found`.
6. **LLM verdict** — Groq with `response_format="json_object"`, JSON-only, three-class signal + confidence + ≤25-word explanation. Sharpened decision rules in the prompt forbid classifying as `similar_exists` based on a single generic word.
7. **Two-sided reconciliation**:
    - LLM `not_found` + heuristic `similar_exists` (real overlap) → upgrade to `similar_exists`.
    - LLM `similar_exists`/`exact_match` + heuristic `not_found` (overlap < 0.05) → downgrade to `not_found`.
    - LLM `similar_exists` + heuristic `exact_match` (overlap ≥ 0.6) → upgrade to `exact_match`.
8. Return `{ signal, explanation, references[≤3] }`.

---

## 13) Experiment plan generation algorithm

`generate_plan(hypothesis, feedback_context=[])`:

1. **Validate** — hypothesis ≥ 20 chars or `400`.
2. **Compose user prompt** — `build_prompt_with_feedback()` selects the 3 most relevant prior feedback entries by experiment-type token overlap and silently injects them as `EXPERT FEEDBACK FROM PRIOR PLANS`.
3. **Call Groq** — through the fallback chain. `response_format="json_object"`, `temperature=0.3`, `max_tokens=8000`.
4. **Sanitise + parse** — strip ``` fences, isolate the outermost `{ … }`, `json.loads`. On JSON failure, send a one-shot repair prompt; on repair failure, fall back to the demo dispatcher.
5. **Assemble** — `_assemble_plan()` walks the dict through `_build_protocol`, `_build_reagents`, `_build_budget`, `_build_timeline`, `_build_validation`. Every helper is defensive against missing keys, wrong types, and empty values.
6. **Return** — strict `ExperimentPlanResponse` Pydantic model.

---

## 14) Learning loop (stretch goal)

Every scientist correction submitted via `POST /api/save-feedback` is appended to `feedback_store.json` as:

```json
{
  "hypothesis": "...",
  "experiment_type": "crispr knockout proliferation",
  "corrections": {
    "protocol":   { "rating": 4, "correction": "Add a Western blot validation step." },
    "reagents":   { "rating": 5, "correction": "" },
    ...
  }
}
```

On the next plan request, `_select_relevant_feedback()` picks up to 3 entries whose `experiment_type` token overlap with the current hypothesis is highest and injects them into the prompt. The judge can:

1. Generate a CRISPR plan.
2. Open Expert Review, give the protocol 3/5, write *"Add a Western blot validation step in addition to TIDE/Sanger."*
3. Click "Start over", regenerate a CRISPR plan for a similar hypothesis.
4. Observe that the new protocol now includes a Western blot step **without** being explicitly re-prompted.

This is the "compounding-learning" demo described in the brief.

---

## 15) Design system

- **Type scale** — Inter (UI) + JetBrains Mono (catalog numbers, code-y values).
- **Palette** — neutral ink navy (`ink-{50..900}`) over warm paper white (`paper`), with a calm clinical accent blue (`accent-{50..900}`). Semantic signal palette (`success` / `warn` / `danger`) keeps the literature QC pill, error toasts, and demo-mode banner unambiguous.
- **Component primitives** in `index.css` (~30): `btn-primary{,-lg}`, `btn-secondary`, `btn-ghost`, `card`, `surface`, `pill-{neutral,accent,success,warn,danger}`, `pill-dot`, `stepper{,-circle,-rail,-label-*}`, `tabs`, `tab-{active,inactive}`, `textarea`, `input`, `label`, `table`, `toast{,-error}`, `skeleton`, animations (`fade-in`, `pulse-dot`).
- **Print stylesheet** — `@media print` reveals all hidden tabs (`[data-print-all="true"] .print-show-all`), drops the slide-over, removes interactive chrome, and rebalances padding for A4.

---

## 16) Quality bar & known limits

**Bar (from the challenge brief):** *Would a real Principal Investigator trust this plan enough to order materials and start running it on Monday?*

What the system reliably gets right today:
- Real catalog numbers from Sigma-Aldrich, Thermo Fisher, ATCC, Promega, Qiagen, IDT, Addgene.
- Realistic non-round prices (e.g. `$42.50`, not `$50`).
- Cited protocol sources (Nature Protocols, Bio-protocol, protocols.io, JOVE, OpenWetWare).
- Specific concentrations, temperatures, and incubation times (no "appropriate temperature").
- ≥4-week timelines with phased Setup → Execution → Analysis → Reporting structure.
- Validation block populated for all 7 keys, with `success_threshold` mirroring the hypothesis numeric threshold.
- Internally consistent budget (`total_usd ≈ Σ breakdown`).

**Known limits:**

- Groq's free tier has a 100K-tokens-per-day cap per primary model. After that the chain falls through to faster/smaller models, then to the demo dispatcher. The yellow banner in the UI surfaces this clearly to the user.
- Catalog numbers, while taken from a real vendor's number space, are not guaranteed to be in stock right now.
- `feedback_store.json` is a flat JSON file — fine for a hackathon demo, not for multi-user production.
- Tavily references occasionally come back without authors; we display "Unknown authors" rather than fabricating.

---

## 17) Deployment (Render + Netlify)

The project is pre-configured for a **split deploy**:

- **Backend** → [Render](https://render.com) (FastAPI, Python 3.11)
- **Frontend** → [Netlify](https://netlify.com) (Vite static build)

The repo ships everything Render needs to deploy the backend with zero manual config beyond setting your secrets.

### Files included for Render

| File | Purpose |
|------|---------|
| `render.yaml` | Blueprint at the repo root — Render auto-detects this and provisions the service with the right rootDir, build/start commands, and env-var skeleton. |
| `backend/runtime.txt` | Pins Python to `3.11.9` so builds are reproducible. |
| `backend/Procfile` | Fallback start command for non-Blueprint deploys (manual web service). |
| `backend/requirements.txt` | Python deps. |

The `main.py` entrypoint reads `PORT`, `ENV`, `RELOAD`, and `CORS_ALLOW_ORIGINS` from environment, so the same code runs in dev and production unchanged.

### 17.1 Deploy the backend on Render — Blueprint flow (recommended)

1. Push this repo to GitHub (private is fine).
2. In Render, click **New +** → **Blueprint** → connect the repo.
3. Render reads `render.yaml` and shows you a service named `ai-scientist-os-backend`. Click **Apply**.
4. The service is created **but the first build will fail** because the secret env vars are still empty. Open the service → **Environment** and set:

   | Key | Value | Notes |
   |-----|-------|-------|
   | `GROQ_API_KEY` | `gsk_...` | From [Groq Console](https://console.groq.com/keys). |
   | `TAVILY_API_KEY` | `tvly-...` | From [Tavily](https://app.tavily.com). Free tier is fine. |
   | `CORS_ALLOW_ORIGINS` | `https://YOUR-APP.netlify.app` | Comma-separated if you have multiple (e.g. preview + custom domain). |

   `PYTHON_VERSION`, `ENV=production`, and `RELOAD=0` are already set by the Blueprint.

5. Click **Manual Deploy → Deploy latest commit**. Build takes ~2 minutes. Once live, hit `https://ai-scientist-os-backend.onrender.com/api/health` — you should see `{"status":"ok","model":"openai/gpt-oss-120b"}`.

### 17.2 Deploy the backend on Render — manual flow (no Blueprint)

If you'd rather wire it up by hand:

1. **New +** → **Web Service** → connect repo.
2. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 65`
   - **Health Check Path:** `/api/health`
3. Add the same env vars as in 17.1.

The included `backend/Procfile` works as a fallback start command if you ever forget to set the field.

### 17.3 Wire your Netlify frontend to the Render backend

On Netlify, open your site → **Site configuration → Environment variables** and add:

```
VITE_API_BASE_URL=https://ai-scientist-os-backend.onrender.com
```

Then trigger a new deploy (Netlify → **Deploys → Trigger deploy → Clear cache and deploy site**) so Vite picks up the new env var. Vite **bakes env vars at build time**, so a redeploy is required — runtime updates won't help.

After the rebuild, the Netlify-hosted UI will start hitting your Render backend. Confirm the wiring by:

1. Open your Netlify URL → DevTools → Network tab.
2. Submit a hypothesis. The `literature-qc` and `generate-plan` requests should fire against `https://ai-scientist-os-backend.onrender.com`, **not** `localhost`.

### 17.4 Things to know about Render's free tier

- **Cold starts (mitigated).** The free instance normally sleeps after ~15 minutes of inactivity, and the first request after sleep takes 30–50 s. **The backend ships with a built-in keep-alive loop that self-pings `RENDER_EXTERNAL_URL/api/health` every 10 minutes**, so the instance never goes idle once it's awake. Render auto-injects `RENDER_EXTERNAL_URL` for you — no extra config needed. See [§17.5](#175-built-in-keep-alive-anti-sleep-loop) below for full details and how to tune or disable it.
- **Ephemeral filesystem.** Anything written to disk at runtime is lost on every redeploy and after ~24 h of idle. This means **`feedback_store.json` is not durable on Render's free plan** — feedback survives within a single container lifecycle but resets on redeploys/sleep. For hackathon demos this is fine; for production swap to a Render Postgres database or attach a Render Disk (paid).
- **One worker.** The start command pins `--workers 1` because the free plan has 512 MB RAM. FastAPI is async so a single worker easily handles dozens of concurrent users.
- **Region.** `render.yaml` sets `region: oregon`. Change to `frankfurt` / `singapore` / `ohio` if you want lower latency to your audience.

### 17.5 Built-in keep-alive (anti-sleep) loop

To survive Render's free-tier 15-minute idle sleep, the backend includes a **self-ping loop** that runs as a FastAPI lifespan background task. Every 10 minutes (configurable) it `GET`s `RENDER_EXTERNAL_URL/api/health`, which counts as live traffic to the Render load balancer and resets the inactivity timer — so the dyno never goes idle.

**How it works**

1. On app startup, the lifespan handler spawns `_keep_alive_loop()` as an `asyncio` task.
2. The loop reads `KEEP_ALIVE_URL` first; if unset, it falls back to `${RENDER_EXTERNAL_URL}/api/health`. (Render auto-injects `RENDER_EXTERNAL_URL` for every web service — you don't need to set it.)
3. It sleeps for `KEEP_ALIVE_INTERVAL_SECONDS` (default 600 s = 10 min, clamped to `[60, 840]`), then issues an `httpx` `GET` and logs the status code.
4. On any network error the loop logs a warning and keeps going — a flaky ping never crashes the worker.
5. On app shutdown, the lifespan cancels the task cleanly.

**Local dev = no-op.** Locally there's no `RENDER_EXTERNAL_URL`, so the loop logs `keep-alive: disabled` and exits immediately. You won't see spurious self-traffic in your dev logs.

**Tuning**

| Variable | Default | Purpose |
|----------|---------|---------|
| `KEEP_ALIVE_ENABLED` | `1` | Set to `0` to disable the loop entirely (e.g. on a paid Render plan where idle sleep doesn't apply). |
| `KEEP_ALIVE_INTERVAL_SECONDS` | `600` | How often to ping. Below 60 s wastes cycles; above 14 min defeats the point (Render sleeps at 15 min). |
| `KEEP_ALIVE_URL` | unset | Override the target URL. Useful if you have a custom domain mapped (e.g. `https://api.yoursite.com/api/health`) and want pings to go through the real edge. |

**Verifying it works**

After deploy, open Render → **Logs** and you should see:

```
keep-alive: scheduled — pinging https://ai-scientist-os-backend.onrender.com/api/health every 600s
```

…followed every 10 minutes by:

```
keep-alive: ping https://ai-scientist-os-backend.onrender.com/api/health -> 200
```

**Why an external pinger is also a good idea**

The internal loop dies when the container dies, so it can't *wake* a service that's already asleep — it can only *keep* an awake one awake. If your service is left alone for hours/days (e.g. overnight before demo day), the first organic visitor still pays a cold-start cost. For belt-and-braces uptime, set up a free external monitor (UptimeRobot, cron-job.org, or BetterStack) hitting `/api/health` every 5 minutes — that guarantees the service is awake even after a deploy or crash recovery. Use the internal loop for steady-state and the external pinger for resilience.

### 17.6 Lock down CORS for production

The dev default in `main.py` is `allow_origins=["*"]`. In production, set `CORS_ALLOW_ORIGINS` to the **exact** Netlify URL (no trailing slash). Multiple origins are comma-separated:

```
CORS_ALLOW_ORIGINS=https://aiscientist.netlify.app,https://aiscientist.com
```

The backend logs the resolved CORS allowlist on startup, so you can confirm the value loaded correctly by checking Render's **Logs** tab right after a deploy.

### 17.7 Smoke test the deployed backend

```bash
# 1) Health
curl https://ai-scientist-os-backend.onrender.com/api/health

# 2) Lit QC
curl -X POST https://ai-scientist-os-backend.onrender.com/api/literature-qc \
  -H "Content-Type: application/json" \
  -d '{"hypothesis":"CRISPR-Cas9 knockout of PCSK9 in primary human hepatocytes will reduce LDL cholesterol secretion by >40% within 7 days."}'

# 3) Plan generation
curl -X POST https://ai-scientist-os-backend.onrender.com/api/generate-plan \
  -H "Content-Type: application/json" \
  -d '{"hypothesis":"CRISPR-Cas9 knockout of PCSK9 in primary human hepatocytes will reduce LDL cholesterol secretion by >40% within 7 days."}'
```

If `/api/health` works but the others time out, your Groq key or Tavily key is missing/invalid — check Render → **Logs**.

---

## 18) Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Showing a cached demo plan` banner | Primary model's daily quota (TPD) is exhausted **and** smaller fallbacks couldn't handle the prompt size. | Wait for the daily Groq quota to reset (00:00 UTC), or set `GROQ_MODEL` to a different primary. |
| Plan generation feels too fast (<5s) and looks generic | Demo dispatcher fired. | Same as above. The banner will be visible. |
| Lit QC returns `not_found` for a clearly published topic | All 3 search backends rate-limited or down. | Re-run; check Tavily / OpenAlex status. |
| Stale Python process holding port 8000 (Windows) | Previous backend wasn't terminated. | `Get-Process python* \| Stop-Process -Force` then re-run `python main.py`. |
| `model_decommissioned` warnings in the log | Groq retired a model in your fallback chain. | The chain self-heals automatically — the warning is informational. To silence it, update `GROQ_FALLBACK_MODELS` in `.env`. |
| Frontend can't reach backend | Wrong `VITE_API_BASE_URL`. | Either start backend on 8000 or set `VITE_API_BASE_URL` in `frontend/.env` (or in Netlify's env panel for production), then **redeploy**. |
| CORS error from the Netlify domain → Render backend | `CORS_ALLOW_ORIGINS` on Render doesn't match the exact Netlify URL. | Set `CORS_ALLOW_ORIGINS=https://your-app.netlify.app` (no trailing slash) on Render and redeploy. |
| First request after demo idle takes 40+ seconds | Render free-plan cold start. | Either upgrade to a paid plan, or hit `/api/health` ~60 s before going on stage. |
| `feedback_store.json` empty after a redeploy | Render's free filesystem is ephemeral. | Move to Render Postgres / Disk for persistence (see §17.4). |

---

## 19) Roadmap

- [ ] Replace `feedback_store.json` with SQLite/Postgres + per-user authentication.
- [ ] Per-section diff view between two plan generations to visualise the learning loop on stage.
- [ ] In-app PDF generation (currently uses `window.print()`).
- [ ] Tighten CORS to a deploy-time allowlist.
- [ ] Add an arXiv source alongside OpenAlex/Tavily/Semantic Scholar.
- [ ] Server-side request quotas + Redis-backed dedupe cache for repeat hypotheses.
- [ ] Move Chart.js from CDN to an npm import for deterministic builds.

---

## 20) Credits

- **Challenge:** *The AI Scientist*, Powered by Fulcrum Science (`arun@fulcrum.science` · `jonas@fulcrum.science`).
- **Built by:** GIKI University team for **MIT Global AI Hackathon 2026** — Challenge 04.
- **Powered by:** Groq · Tavily · OpenAlex · Semantic Scholar.
- **Stack:** FastAPI · Pydantic v2 · React 18 · Vite 5 · Tailwind CSS 3.4 · Chart.js.

> *"What accelerated COVID-19 vaccine development wasn't a new idea — the mRNA hypothesis had existed for decades. It was the ability to move from hypothesis to executable experiment at unprecedented speed. That's the gap you're closing."* — Challenge brief.
