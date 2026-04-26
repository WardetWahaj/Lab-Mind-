from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Union
from contextlib import asynccontextmanager
import os
import json
import re
import logging
import asyncio
import httpx
from dotenv import load_dotenv

from literature import run_literature_qc
from prompts import SYSTEM_PROMPT, build_prompt_with_feedback
from groq import Groq

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Centralised model selection so we never hit the old "gemini_model not defined" regression.
# We try the highest-quality model first and fall back through smaller models if the
# 70B's daily token quota is exhausted (Groq's free tier resets at 00:00 UTC).
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv(
        "GROQ_FALLBACK_MODELS",
        # Curated chain of currently active Groq production models, ordered
        # high-quality → faster/lighter. Verified against /v1/models on
        # 2026-04-26 — earlier choices like gemma2-9b-it, llama3-70b-8192,
        # llama3-8b-8192, llama-3.2-90b-text-preview, mixtral-8x7b-32768
        # were all decommissioned by Groq.
        "openai/gpt-oss-120b,"
        "meta-llama/llama-4-scout-17b-16e-instruct,"
        "qwen/qwen3-32b,"
        "openai/gpt-oss-20b,"
        "groq/compound,"
        "llama-3.1-8b-instant",
    ).split(",")
    if m.strip()
]
GENERATION_MODEL_CHAIN = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
# Backwards compatibility for the existing /api/health response.
GENERATION_MODEL = PRIMARY_MODEL

def _make_groq_client() -> Optional[Groq]:
    """Build the Groq client lazily.

    A missing/invalid GROQ_API_KEY must NOT crash the FastAPI process at
    import time — Render would just exit with status 1 and the operator
    would see no traceback. Instead we log a clear warning and return None;
    every LLM call site already has a demo-fallback path that handles this.
    """
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        logger.warning(
            "GROQ_API_KEY is not set — LLM calls will fall back to the demo "
            "dispatcher. Set GROQ_API_KEY in your hosting environment "
            "(e.g. Render → Environment) to enable real plan generation."
        )
        return None
    try:
        return Groq(api_key=api_key)
    except Exception as exc:  # noqa: BLE001 — broad on purpose, keeps the app up
        logger.error(f"Groq client failed to initialise ({exc!r}); demo mode active.")
        return None


groq_client: Optional[Groq] = _make_groq_client()


def _is_retryable_groq_error(exc: Exception) -> bool:
    """Return True for errors that mean 'try the next model in the chain'.

    Covers:
      - Daily-token / rate-limit (429)
      - Strict JSON-mode validation failures (small models sometimes emit
        invalid JSON; the 70B is much more reliable).
      - Decommissioned-model errors (so the chain heals itself).
      - Generic 5xx server errors.
    """
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "rate_limit",
            "quota",
            "too many requests",
            "tpd", "rpd",
            "json_validate_failed",
            "failed to generate json",
            "model_decommissioned",
            "decommissioned",
            "model_not_found",
            "503", "502", "500",
            "service unavailable",
            "internal server error",
        )
    )


# Backwards-compatible alias used elsewhere for the rate-limit check only.
def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(token in msg for token in ("429", "rate_limit", "quota", "too many requests", "tpd", "rpd"))


def _groq_chat_with_fallback(messages: list, *, max_tokens: int, temperature: float, response_format: Optional[dict] = None) -> Tuple[str, str]:
    """Run a Groq chat completion, falling through the model chain on retryable errors.

    Returns (response_text, model_used). Raises the last exception only when
    every model in the chain has been exhausted.
    """
    if groq_client is None:
        raise RuntimeError(
            "Groq client is not configured (GROQ_API_KEY missing or invalid). "
            "Falling back to the demo dispatcher."
        )

    last_exc: Optional[Exception] = None
    for model in GENERATION_MODEL_CHAIN:
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            response = groq_client.chat.completions.create(**kwargs)
            text = (response.choices[0].message.content or "").strip()
            if model != PRIMARY_MODEL:
                logger.info(f"Used Groq fallback model: {model}")
            return text, model
        except Exception as exc:
            last_exc = exc
            if _is_retryable_groq_error(exc):
                logger.warning(f"Groq model {model} returned retryable error; trying next fallback. Reason: {exc}")
                continue
            logger.error(f"Groq model {model} hard error (non-retryable): {exc}")
            break
    err = last_exc or RuntimeError("Unknown Groq error")
    raise err

# ---------------------------------------------------------------------------
# Keep-alive loop (Render free-tier anti-sleep)
# ---------------------------------------------------------------------------
# Render's free plan spins a service down after ~15 min of zero traffic, and
# the next request takes 30–50 s to wake it. We self-ping our own /api/health
# every KEEP_ALIVE_INTERVAL_SECONDS (default 600 s = 10 min, well under the
# 15-min idle threshold) so the instance never goes idle. The loop is a no-op
# locally because RENDER_EXTERNAL_URL is only injected by Render, so dev
# environments aren't affected.
# ---------------------------------------------------------------------------


def _resolve_keep_alive_url() -> str:
    """Decide which URL the keep-alive loop should ping (or '' to disable)."""
    explicit = os.getenv("KEEP_ALIVE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return f"{render_url}/api/health"
    return ""


async def _keep_alive_loop() -> None:
    """Periodic self-ping to prevent Render free-tier sleep.

    Cancellable via the FastAPI lifespan shutdown. Transient errors are logged
    but never propagate, so a flaky pings never crashes the worker.
    """
    if os.getenv("KEEP_ALIVE_ENABLED", "1").strip() == "0":
        logger.info("keep-alive: disabled via KEEP_ALIVE_ENABLED=0")
        return

    target_url = _resolve_keep_alive_url()
    if not target_url:
        logger.info(
            "keep-alive: disabled (no KEEP_ALIVE_URL or RENDER_EXTERNAL_URL set — "
            "this is expected in local dev)"
        )
        return

    try:
        interval = int(os.getenv("KEEP_ALIVE_INTERVAL_SECONDS", "600"))
    except ValueError:
        interval = 600
    # Clamp to [60s, 14min]. Render's idle threshold is 15min, so anything
    # above ~14min defeats the point. Below 60s would just waste cycles.
    interval = max(60, min(interval, 14 * 60))

    logger.info(
        f"keep-alive: scheduled — pinging {target_url} every {interval}s"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            try:
                await asyncio.sleep(interval)
                response = await client.get(target_url)
                logger.info(
                    f"keep-alive: ping {target_url} -> {response.status_code}"
                )
            except asyncio.CancelledError:
                logger.info("keep-alive: loop cancelled, exiting cleanly")
                raise
            except Exception as exc:  # noqa: BLE001 — never let a ping error crash the worker
                logger.warning(f"keep-alive: ping failed ({exc}); will retry")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan: spin up the keep-alive loop, tear it down on exit."""
    task = asyncio.create_task(_keep_alive_loop(), name="keep-alive-loop")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="Lab Mind",
    description="From hypothesis to runnable experiment plan",
    version="1.1.0",
    lifespan=lifespan,
)


def _parse_cors_origins() -> List[str]:
    """Read allowed CORS origins from CORS_ALLOW_ORIGINS env (comma-separated).

    Defaults to '*' (open) so local dev and hackathon demos work out of the
    box. In production (e.g. Render) set this to your Netlify URL, e.g.
        CORS_ALLOW_ORIGINS=https://your-app.netlify.app,https://your-app.com
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


_CORS_ORIGINS = _parse_cors_origins()
logger.info(f"CORS allowed origins: {_CORS_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # allow_credentials must be False whenever allow_origins=["*"] (CORS spec).
    # If you set CORS_ALLOW_ORIGINS to a specific domain list, credentials
    # would be safe to enable — but we don't use cookies, so we leave it off.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic models
# ============================================================================


class HypothesisInput(BaseModel):
    hypothesis: str


class ReferencePaper(BaseModel):
    title: str
    authors: str
    year: int
    url: str
    source: Optional[str] = None


class LiteratureQCResponse(BaseModel):
    signal: str  # "not_found" | "similar_exists" | "exact_match"
    explanation: Optional[str] = ""
    references: List[ReferencePaper]


class ProtocolStep(BaseModel):
    step: int
    title: str
    description: str
    duration: str
    safety_note: str = ""
    source: str = ""


class Reagent(BaseModel):
    name: str
    quantity: float = 0.0
    unit: str = ""
    concentration: str = "N/A"
    supplier: str = ""
    catalog_number: str = ""
    unit_price_usd: float = 0.0
    total_cost_usd: float = 0.0
    notes: str = ""


class BudgetBreakdown(BaseModel):
    category: str
    amount_usd: float = 0.0


class Budget(BaseModel):
    total_usd: float = 0.0
    currency_note: str = "All prices in USD, illustrative estimate"
    breakdown: List[BudgetBreakdown] = Field(default_factory=list)


class TimelinePhase(BaseModel):
    week: Optional[int] = None
    phase: str = "Phase"
    tasks: Optional[List[str]] = None
    milestone: Optional[str] = None
    depends_on: Optional[List] = None
    start_day: Optional[int] = None
    duration_days: Optional[int] = None
    description: Optional[str] = None


class Validation(BaseModel):
    primary_metric: str = ""
    success_threshold: str = ""
    control_condition: str = ""
    statistical_test: str = ""
    sample_size: str = ""
    failure_criteria: str = ""
    reporting_standard: str = ""


class ExperimentPlanResponse(BaseModel):
    protocol: List[ProtocolStep]
    reagents: List[Reagent]
    budget: Budget
    timeline: List[TimelinePhase]
    validation: Validation


class FeedbackCorrection(BaseModel):
    rating: int
    correction: str


class SaveFeedbackInput(BaseModel):
    hypothesis: str
    experiment_type: str
    corrections: dict


class SaveFeedbackResponse(BaseModel):
    saved: bool


# ============================================================================
# Helpers
# ============================================================================


_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _coerce_float(value, default: float = 0.0) -> float:
    """Best-effort conversion of LLM output into a float.

    LLMs frequently return strings like "100 mg", "~45.00", "$1,200" or
    even nested dicts. We strip non-numeric noise and fall back to default
    instead of raising a Pydantic validation error.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        match = _NUMERIC_RE.search(cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return default
    return default


def _coerce_int(value, default: int = 0) -> int:
    return int(_coerce_float(value, default=default))


def _coerce_str(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def _coerce_str_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_coerce_str(v) for v in value if v not in (None, "")]
    if isinstance(value, str):
        # Split on common separators when the LLM returns a single string.
        parts = re.split(r"\s*[\n;]\s*|\s*,\s*(?=[A-Z])", value)
        return [p.strip() for p in parts if p.strip()]
    return [_coerce_str(value)]


def _sanitise_json_text(text: str) -> str:
    """Strip markdown fences and isolate the outermost JSON object."""
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json or ``` openers and trailing fence.
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    # Some models still wrap JSON in prose. Grab the first {...} block.
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
    return text


_DEMO_NOTE = (
    "DEMO MODE — LLM provider unavailable (e.g. rate-limited or quota exhausted). "
    "This is an illustrative cached plan, not a fresh generation. Please retry shortly."
)


def _demo_cryopreservation_plan() -> ExperimentPlanResponse:
    return ExperimentPlanResponse(
        protocol=[
            ProtocolStep(step=1, title="Cell preparation and seeding", description="Thaw HeLa cells (ATCC CCL-2) into pre-warmed DMEM + 10% FBS + 1% Pen/Strep. Seed at 2.5×10^5 cells/well in 6-well plates. Incubate 24 h at 37 °C, 5% CO2.", duration="2 days", safety_note="BSL-2: handle in laminar flow hood; dispose of waste in biohazard bins.", source="protocols.io: Mammalian cell thaw and seeding (general)"),
            ProtocolStep(step=2, title="Cryoprotectant solution preparation", description="Prepare freezing medium with either 10% DMSO (control) or 0.5 M trehalose + 5% DMSO (treatment) in DMEM. Sterile filter (0.22 µm). Pre-chill on ice.", duration="1 hour", safety_note="DMSO is a skin penetrant; wear nitrile gloves.", source="Bio-protocol bio-101 Cryopreservation series"),
            ProtocolStep(step=3, title="Controlled-rate freezing", description="Aliquot 1 mL/cryovial at 1×10^6 cells/mL. Freeze in Mr. Frosty container at -1 °C/min to -80 °C overnight, then transfer to liquid nitrogen vapour phase.", duration="24 hours", safety_note="Use cryogloves and face shield when handling LN2.", source="Nature Protocols: Standard mammalian cryopreservation"),
            ProtocolStep(step=4, title="Thaw and post-thaw viability", description="Rapid-thaw vials in 37 °C water bath for 90 s. Resuspend dropwise into 9 mL pre-warmed media. Centrifuge 200×g 5 min, resuspend in fresh media. Plate and quantify viability at 0, 24, 48 h via Trypan blue and CellTiter-Glo.", duration="3 days", safety_note="", source="protocols.io: HeLa thaw and recovery"),
        ],
        reagents=[
            Reagent(name="DMEM, high glucose", quantity=500, unit="mL", concentration="1×", supplier="Thermo Fisher", catalog_number="11965118", unit_price_usd=42.50, total_cost_usd=85.00, notes="Store at 4 °C; warm to 37 °C before use."),
            Reagent(name="Fetal Bovine Serum, qualified", quantity=50, unit="mL", concentration="10% v/v", supplier="Thermo Fisher", catalog_number="26140079", unit_price_usd=520.00, total_cost_usd=520.00, notes="Heat-inactivate at 56 °C for 30 min if required."),
            Reagent(name="DMSO, sterile-filtered", quantity=100, unit="mL", concentration="cell-culture grade", supplier="Sigma-Aldrich", catalog_number="D2650", unit_price_usd=68.00, total_cost_usd=68.00, notes="Hygroscopic; aliquot and store at -20 °C."),
            Reagent(name="D-(+)-Trehalose dihydrate", quantity=25, unit="g", concentration="0.5 M working", supplier="Sigma-Aldrich", catalog_number="T9531", unit_price_usd=85.00, total_cost_usd=85.00, notes="Filter-sterilise (0.22 µm) before use."),
            Reagent(name="HeLa cell line", quantity=1, unit="vial", concentration="N/A", supplier="ATCC", catalog_number="CCL-2", unit_price_usd=525.00, total_cost_usd=525.00, notes="MTA required."),
            Reagent(name="CellTiter-Glo 2.0", quantity=10, unit="mL", concentration="ready-to-use", supplier="Promega", catalog_number="G9241", unit_price_usd=295.00, total_cost_usd=295.00, notes="Store at -20 °C; equilibrate to RT before use."),
        ],
        budget=Budget(
            total_usd=4_780.00,
            currency_note=_DEMO_NOTE,
            breakdown=[
                BudgetBreakdown(category="Reagents & Consumables", amount_usd=1_578.00),
                BudgetBreakdown(category="Equipment & Rental", amount_usd=900.00),
                BudgetBreakdown(category="Cell Lines / Biological Materials", amount_usd=525.00),
                BudgetBreakdown(category="Labour (estimated)", amount_usd=1_343.00),
                BudgetBreakdown(category="Contingency (10%)", amount_usd=434.00),
            ],
        ),
        timeline=[
            TimelinePhase(week=1, phase="Setup", tasks=["Order reagents", "Validate ATCC HeLa thaw"], milestone="Materials in lab and cells expanding"),
            TimelinePhase(week=2, phase="Setup", tasks=["Prepare both freezing media", "Confirm cell counts and viability"], milestone="Freezing media QC complete"),
            TimelinePhase(week=3, phase="Execution", tasks=["Freeze control + trehalose conditions", "Store at LN2 ≥7 days"], milestone="Cryostorage achieved"),
            TimelinePhase(week=4, phase="Execution", tasks=["Thaw all conditions", "Quantify 0/24/48 h viability"], milestone="Primary viability data"),
            TimelinePhase(week=5, phase="Analysis", tasks=["Run statistics (two-sided t-test)", "Plot survival curves"], milestone="Statistical comparison"),
            TimelinePhase(week=6, phase="Reporting", tasks=["Draft results", "Internal PI review"], milestone="Report drafted"),
        ],
        validation=Validation(
            primary_metric="Post-thaw viability (% viable cells at 24 h)",
            success_threshold="Trehalose group shows ≥15 percentage points higher viability than DMSO control (p<0.05)",
            control_condition="Standard 10% DMSO freezing medium",
            statistical_test="Two-sided Student's t-test on independent biological replicates",
            sample_size="n=6 biological replicates per condition (power 0.8, effect size 1.0)",
            failure_criteria="Trehalose viability is ≤ control + 5 pp, or trehalose group shows >20% reduction in proliferation at 48 h",
            reporting_standard="ISO 20391-1 cell counting; report mean ± SD with 95% CI",
        ),
    )


def _demo_crispr_plan() -> ExperimentPlanResponse:
    return ExperimentPlanResponse(
        protocol=[
            ProtocolStep(step=1, title="sgRNA design and cloning", description="Design 3 candidate sgRNAs targeting target gene exon 2-4 using CRISPick. Clone each into pSpCas9(BB)-2A-GFP (PX458) via BbsI digest + T4 ligation. Verify by Sanger.", duration="5 days", safety_note="BSL-2; lentivirus may be involved downstream — handle with appropriate containment.", source="Nature Protocols: Ran et al. Genome engineering using CRISPR-Cas9 (2013)"),
            ProtocolStep(step=2, title="Cell line transfection", description="Seed HEK293T cells at 4×10^5/well in 6-well plates. Transfect 1 µg PX458-sgRNA with Lipofectamine 3000 in Opti-MEM. Incubate 48 h.", duration="3 days", safety_note="Wear lab coat and gloves when handling Lipofectamine.", source="protocols.io: Lipofectamine 3000 mammalian transfection"),
            ProtocolStep(step=3, title="GFP+ single-cell sorting", description="Trypsinise, resuspend in PBS + 2% FBS + DAPI. Sort GFP+ DAPI- single cells into 96-well plates with conditioned media on a BD FACSAria.", duration="1 day", safety_note="Use Class II BSC for sorting; aerosol risk.", source="Bio-protocol bio-101.3050 single-cell FACS sorting"),
            ProtocolStep(step=4, title="Clonal expansion and genotyping", description="Expand clones over 2-3 weeks. Extract gDNA (Qiagen DNeasy). Amplify the edited locus and run TIDE / Sanger to confirm indels and select knockouts.", duration="3 weeks", safety_note="", source="protocols.io: TIDE analysis of CRISPR edits"),
            ProtocolStep(step=5, title="Phenotypic readout", description="Plate edited and parental clones at 5×10^3 cells/well in 96-well plates. Measure proliferation by CellTiter-Glo at days 0, 3, 7, 14. Run alongside Western blot for protein loss.", duration="2 weeks", safety_note="", source="Promega TM288 CellTiter-Glo technical manual"),
        ],
        reagents=[
            Reagent(name="pSpCas9(BB)-2A-GFP (PX458)", quantity=1, unit="vial", concentration="N/A", supplier="Addgene", catalog_number="48138", unit_price_usd=85.00, total_cost_usd=85.00, notes="MTA required."),
            Reagent(name="HEK293T cell line", quantity=1, unit="vial", concentration="N/A", supplier="ATCC", catalog_number="CRL-3216", unit_price_usd=525.00, total_cost_usd=525.00, notes="MTA required; expand on receipt."),
            Reagent(name="Lipofectamine 3000", quantity=1.5, unit="mL", concentration="ready-to-use", supplier="Thermo Fisher", catalog_number="L3000015", unit_price_usd=545.00, total_cost_usd=545.00, notes="Store at 4 °C."),
            Reagent(name="DMEM, high glucose", quantity=500, unit="mL", concentration="1×", supplier="Thermo Fisher", catalog_number="11965118", unit_price_usd=42.50, total_cost_usd=85.00, notes="Pre-warm before use."),
            Reagent(name="Custom sgRNA oligos (3 pairs)", quantity=6, unit="oligo", concentration="100 µM", supplier="IDT", catalog_number="custom", unit_price_usd=22.00, total_cost_usd=132.00, notes="Order as Ultramers if needed."),
            Reagent(name="DNeasy Blood & Tissue Kit", quantity=1, unit="kit (50 preps)", concentration="N/A", supplier="Qiagen", catalog_number="69504", unit_price_usd=395.00, total_cost_usd=395.00, notes=""),
            Reagent(name="CellTiter-Glo 2.0", quantity=10, unit="mL", concentration="ready-to-use", supplier="Promega", catalog_number="G9241", unit_price_usd=295.00, total_cost_usd=295.00, notes="Store at -20 °C."),
        ],
        budget=Budget(
            total_usd=6_512.00,
            currency_note=_DEMO_NOTE,
            breakdown=[
                BudgetBreakdown(category="Reagents & Consumables", amount_usd=2_062.00),
                BudgetBreakdown(category="Equipment & Rental", amount_usd=1_400.00),
                BudgetBreakdown(category="Cell Lines / Biological Materials", amount_usd=525.00),
                BudgetBreakdown(category="Labour (estimated)", amount_usd=1_933.00),
                BudgetBreakdown(category="Contingency (10%)", amount_usd=592.00),
            ],
        ),
        timeline=[
            TimelinePhase(week=1, phase="Setup", tasks=["Design sgRNAs in CRISPick", "Order oligos and PX458 plasmid"], milestone="sgRNA design complete and ordered"),
            TimelinePhase(week=2, phase="Setup", tasks=["Clone sgRNAs into PX458", "Sanger-verify constructs"], milestone="3 verified sgRNA constructs"),
            TimelinePhase(week=3, phase="Execution", tasks=["Transfect HEK293T", "FACS-sort GFP+ single cells"], milestone="96-well plate of single-cell clones"),
            TimelinePhase(week=4, phase="Execution", tasks=["Expand clones", "Begin gDNA extractions"], milestone="≥10 clones expanded"),
            TimelinePhase(week=5, phase="Execution", tasks=["TIDE / Sanger genotyping", "Confirm knockout clones"], milestone="≥3 confirmed KO clones"),
            TimelinePhase(week=6, phase="Analysis", tasks=["CellTiter-Glo proliferation timecourse", "Western blot for protein loss"], milestone="Phenotype data acquired"),
            TimelinePhase(week=7, phase="Reporting", tasks=["Statistics", "Draft figures and results"], milestone="Report drafted"),
        ],
        validation=Validation(
            primary_metric="Cell proliferation rate (CellTiter-Glo RLU vs day 0) and confirmed knockout rate",
            success_threshold="≥3 verified clones with biallelic indels and ≥30% reduction in proliferation at day 14 vs parental (p<0.05)",
            control_condition="Parental HEK293T cells transfected with non-targeting sgRNA",
            statistical_test="Two-way ANOVA with Tukey HSD post-hoc on time × genotype",
            sample_size="n=3 independent KO clones × 4 technical replicates × 4 timepoints",
            failure_criteria="No biallelic indels in 0/20 sequenced clones, OR no significant proliferation difference vs control",
            reporting_standard="MIQE-compliant qPCR if used; ARRIVE not applicable (in vitro)",
        ),
    )


def _demo_microbiome_plan() -> ExperimentPlanResponse:
    return ExperimentPlanResponse(
        protocol=[
            ProtocolStep(step=1, title="Animal randomisation and acclimation", description="Acclimate 24 male C57BL/6J mice (8 weeks) for 7 days on standard chow. Randomise into control (n=12) and probiotic (n=12) groups stratified by weight.", duration="1 week", safety_note="ARRIVE 2.0 reporting; IACUC protocol approval required.", source="Bio-protocol bio-101 mouse husbandry general"),
            ProtocolStep(step=2, title="Probiotic gavage daily for 4 weeks", description="Treatment group: 1×10^9 CFU Lactobacillus rhamnosus GG (ATCC 53103) in 200 µL PBS by oral gavage daily at 9:00 AM. Control: 200 µL sterile PBS.", duration="4 weeks", safety_note="Use sterile gavage needles; proper restraint training required.", source="Nature Protocols: Oral gavage in mice (Turner et al.)"),
            ProtocolStep(step=3, title="FITC-dextran intestinal permeability assay", description="Fast 4 h. Gavage 600 mg/kg FITC-dextran (4 kDa). Collect serum at 4 h. Read fluorescence at 485/528 nm against standard curve.", duration="1 day", safety_note="FITC is a photosensitiser; protect from light.", source="protocols.io: FITC-dextran intestinal permeability assay"),
            ProtocolStep(step=4, title="Tissue harvest for tight-junction qPCR/IHC", description="Euthanise (CO2 + cervical dislocation). Collect distal ileum and colon. Process for RNA (RNAlater) and IHC (4% PFA fix). Run qPCR for Cldn1/Ocln/Tjp1.", duration="2 days", safety_note="Comply with institutional animal euthanasia SOPs.", source="protocols.io: Mouse intestinal tissue dissection and processing"),
        ],
        reagents=[
            Reagent(name="C57BL/6J mice (male, 8 wk)", quantity=24, unit="animals", concentration="N/A", supplier="Jackson Lab / Charles River", catalog_number="000664", unit_price_usd=42.00, total_cost_usd=1_008.00, notes="Per-animal cost; husbandry charged separately."),
            Reagent(name="Lactobacillus rhamnosus GG", quantity=1, unit="vial", concentration="N/A", supplier="ATCC", catalog_number="53103", unit_price_usd=535.00, total_cost_usd=535.00, notes="MTA required; expand and titre before use."),
            Reagent(name="FITC-dextran (4 kDa)", quantity=1, unit="g", concentration="600 mg/kg dosing", supplier="Sigma-Aldrich", catalog_number="46944", unit_price_usd=180.00, total_cost_usd=180.00, notes="Light-sensitive; aliquot."),
            Reagent(name="MRS Broth", quantity=500, unit="g", concentration="N/A", supplier="Sigma-Aldrich", catalog_number="69966", unit_price_usd=98.00, total_cost_usd=98.00, notes="For LGG culture."),
            Reagent(name="RNAlater", quantity=100, unit="mL", concentration="N/A", supplier="Thermo Fisher", catalog_number="AM7020", unit_price_usd=120.00, total_cost_usd=120.00, notes=""),
            Reagent(name="qPCR primers Cldn1/Ocln/Tjp1/Gapdh", quantity=8, unit="oligo", concentration="100 µM", supplier="IDT", catalog_number="custom", unit_price_usd=18.00, total_cost_usd=144.00, notes=""),
        ],
        budget=Budget(
            total_usd=8_915.00,
            currency_note=_DEMO_NOTE,
            breakdown=[
                BudgetBreakdown(category="Reagents & Consumables", amount_usd=1_077.00),
                BudgetBreakdown(category="Equipment & Rental", amount_usd=1_500.00),
                BudgetBreakdown(category="Cell Lines / Biological Materials", amount_usd=1_543.00),
                BudgetBreakdown(category="Labour (estimated)", amount_usd=3_985.00),
                BudgetBreakdown(category="Contingency (10%)", amount_usd=810.00),
            ],
        ),
        timeline=[
            TimelinePhase(week=1, phase="Setup", tasks=["IACUC approval review", "Order animals and reagents"], milestone="Approval + materials in lab"),
            TimelinePhase(week=2, phase="Setup", tasks=["Acclimation week 1", "LGG culture and titre"], milestone="Animals acclimated, LGG ready"),
            TimelinePhase(week=3, phase="Execution", tasks=["Begin daily gavage (week 1 of 4)"], milestone="Treatment day 7"),
            TimelinePhase(week=4, phase="Execution", tasks=["Continue gavage (week 2)"], milestone="Treatment day 14"),
            TimelinePhase(week=5, phase="Execution", tasks=["Continue gavage (week 3)"], milestone="Treatment day 21"),
            TimelinePhase(week=6, phase="Execution", tasks=["Continue gavage (week 4)", "FITC-dextran assay endpoint"], milestone="Permeability data acquired"),
            TimelinePhase(week=7, phase="Analysis", tasks=["Tissue harvest", "qPCR for tight-junction markers"], milestone="Molecular data acquired"),
            TimelinePhase(week=8, phase="Reporting", tasks=["Statistics", "Draft results / figures"], milestone="Report drafted"),
        ],
        validation=Validation(
            primary_metric="Serum FITC-dextran fluorescence (µg/mL) at 4 h post-gavage",
            success_threshold="Probiotic group shows ≥30% reduction in serum FITC vs control (p<0.05)",
            control_condition="Vehicle (200 µL sterile PBS) gavage matched 1:1",
            statistical_test="Two-sided Student's t-test (or Mann-Whitney if non-normal); n adjusted for FDR",
            sample_size="n=12 per group (power 0.8 to detect 30% effect, α=0.05)",
            failure_criteria="No significant difference in FITC permeability AND no upregulation of Cldn1/Ocln",
            reporting_standard="ARRIVE 2.0 for animal experiments; MIQE for qPCR",
        ),
    )


def _is_compute_or_ml_hypothesis(text: str) -> bool:
    """Detect ML / signal-processing / software-engineering style hypotheses
    so we don't show wet-lab reagents for them."""
    tokens = (
        "deepfake", "deep-fake", "syncnet", "asvspoof", "spoof",
        "mel-spectrogram", "mel spectrogram", "spectrogram",
        "neural network", "neural-network", "transformer", "convnet",
        "resnet", "cnn ", "lstm", "gan ", "vae ", "diffusion model",
        "f1-score", "f1 score", "accuracy on", "auc ", "roc ",
        "classification model", "detection model", "segmentation model",
        "training set", "validation set", "test set", "fine-tune",
        "fine tune", "pretrained", "embedding model", "language model",
        "llm ", "nlp ", "computer vision", "object detection",
        "speech recognition", "phoneme", "acoustic feature",
        "pytorch", "tensorflow", "scikit-learn", "huggingface",
        "dataset", "benchmark", "kaggle", "imagenet", "coco dataset",
    )
    return any(tok in text for tok in tokens)


def _build_skeleton_plan_from_hypothesis(hypothesis: str) -> ExperimentPlanResponse:
    """Last-resort plan synthesised from the hypothesis text itself.

    Used when (a) all live Groq models fail AND (b) no cached template
    fits the topic. Avoids the previous failure mode of returning a
    cryopreservation wet-lab plan for an ML/signal-processing question.
    """
    h = hypothesis.strip() or "the stated hypothesis"
    h_short = h if len(h) <= 220 else h[:217] + "..."

    if _is_compute_or_ml_hypothesis(h.lower()):
        protocol = [
            ProtocolStep(step=1, title="Define dataset and evaluation split",
                         description=f"Curate train/validation/test partitions appropriate for: {h_short}",
                         duration="3 days", source="ML best practice (no live source — provider unavailable)"),
            ProtocolStep(step=2, title="Implement baseline model",
                         description="Reproduce the strongest published baseline on the same split as a reference point.",
                         duration="1 week", source="Cited prior work in the literature QC tab"),
            ProtocolStep(step=3, title="Implement proposed method",
                         description="Implement the novel architecture / signal-processing pipeline described in the hypothesis.",
                         duration="2 weeks", source="Hypothesis text"),
            ProtocolStep(step=4, title="Train with cross-validation",
                         description="Train with k-fold cross-validation, log metrics, save checkpoints.",
                         duration="1-2 weeks", source="Standard ML protocol"),
            ProtocolStep(step=5, title="Evaluate vs. baseline",
                         description="Run the test split, report all metrics declared in the hypothesis, with confidence intervals.",
                         duration="3 days", source="Standard ML protocol"),
            ProtocolStep(step=6, title="Ablation studies",
                         description="Disable each major component to attribute the gain to specific design choices.",
                         duration="1 week", source="Standard ML protocol"),
        ]
        reagents = [
            Reagent(name="GPU compute time (A100 80GB)", quantity=200, unit="GPU-hour",
                    supplier="Cloud provider (AWS/GCP/Azure)", catalog_number="p4d.24xlarge / a2-highgpu",
                    unit_price_usd=3.5, total_cost_usd=700.0, notes="Adjust based on dataset size"),
            Reagent(name="Storage (object store)", quantity=500, unit="GB-month",
                    supplier="Cloud provider", catalog_number="S3 / GCS",
                    unit_price_usd=0.025, total_cost_usd=12.5, notes="For datasets, checkpoints, logs"),
            Reagent(name="Experiment tracking (W&B / MLflow)", quantity=1, unit="seat",
                    supplier="Weights & Biases", catalog_number="Personal-Pro",
                    unit_price_usd=50.0, total_cost_usd=50.0, notes="Optional but recommended"),
        ]
        budget = Budget(
            total_usd=2762.5,
            currency_note=_DEMO_NOTE,
            breakdown=[
                BudgetBreakdown(category="Compute (GPU-hours)", amount_usd=700.0),
                BudgetBreakdown(category="Storage & Tracking", amount_usd=62.5),
                BudgetBreakdown(category="Labour (estimated)", amount_usd=1800.0),
                BudgetBreakdown(category="Contingency (10%)", amount_usd=200.0),
            ],
        )
        timeline = [
            TimelinePhase(week=1, phase="Setup", tasks=["Define dataset and evaluation split"], milestone="Splits frozen, baseline reproduced", depends_on=[]),
            TimelinePhase(week=2, phase="Execution", tasks=["Implement proposed method"], milestone="Method runs end-to-end", depends_on=["Define dataset and evaluation split"]),
            TimelinePhase(week=3, phase="Execution", tasks=["Train with cross-validation"], milestone="All folds trained", depends_on=["Implement proposed method"]),
            TimelinePhase(week=4, phase="Analysis", tasks=["Evaluate vs. baseline", "Ablation studies"], milestone="Final metrics + ablations", depends_on=["Train with cross-validation"]),
            TimelinePhase(week=5, phase="Reporting", tasks=["Write report"], milestone="Manuscript draft", depends_on=["Evaluate vs. baseline"]),
        ]
        validation = Validation(
            primary_metric="Reported metric in hypothesis (e.g., F1-score on declared benchmark)",
            success_threshold="Threshold stated in hypothesis (e.g., F1 ≥ 0.92)",
            control_condition="Strongest published baseline on identical split",
            statistical_test="Paired bootstrap or McNemar's test across folds",
            sample_size="All test-set samples (k-fold CV)",
            failure_criteria="Metric below stated threshold OR not statistically better than baseline",
            reporting_standard="Follow the relevant benchmark's official protocol",
        )
        return ExperimentPlanResponse(
            protocol=protocol, reagents=reagents, budget=budget,
            timeline=timeline, validation=validation,
        )

    # Generic wet-lab skeleton (when topic is biology-ish but no template
    # matches well). Still hypothesis-aware so titles aren't misleading.
    protocol = [
        ProtocolStep(step=1, title="Define experimental groups and controls",
                     description=f"Specify treatment, vehicle, and positive controls for: {h_short}",
                     duration="1 week", source="Best-practice experimental design"),
        ProtocolStep(step=2, title="Procure biological materials and reagents",
                     description="Order specimens, reagents, and consumables called out by the hypothesis.",
                     duration="2 weeks", source="Vendor lead times"),
        ProtocolStep(step=3, title="Pilot run (n=3) to lock parameters",
                     description="Run a small pilot to validate the assay window before the main cohort.",
                     duration="1 week", source="Standard pilot protocol"),
        ProtocolStep(step=4, title="Main experimental cohort",
                     description="Run the powered cohort following the pre-registered protocol.",
                     duration="3-4 weeks", source="Power calculation"),
        ProtocolStep(step=5, title="Primary endpoint measurement",
                     description="Measure the primary outcome variable named in the hypothesis.",
                     duration="1 week", source="Hypothesis text"),
        ProtocolStep(step=6, title="Statistical analysis & reporting",
                     description="Apply pre-registered statistical test, report effect size + 95% CI.",
                     duration="1 week", source="Statistical pre-registration"),
    ]
    reagents = [
        Reagent(name="Sample collection / specimen kit", quantity=1, unit="kit",
                supplier="To be selected by lab", catalog_number="N/A",
                unit_price_usd=200.0, total_cost_usd=200.0, notes="Select per assay format"),
        Reagent(name="Primary assay reagent", quantity=1, unit="kit",
                supplier="To be selected", catalog_number="N/A",
                unit_price_usd=400.0, total_cost_usd=400.0, notes="Match to primary endpoint"),
        Reagent(name="Statistical analysis software", quantity=1, unit="seat",
                supplier="GraphPad / R / Python", catalog_number="-",
                unit_price_usd=0.0, total_cost_usd=0.0, notes="R/Python free; GraphPad licensed"),
    ]
    budget = Budget(
        total_usd=4500.0,
        currency_note=_DEMO_NOTE,
        breakdown=[
            BudgetBreakdown(category="Reagents & Consumables", amount_usd=1800.0),
            BudgetBreakdown(category="Equipment & Rental", amount_usd=600.0),
            BudgetBreakdown(category="Labour (estimated)", amount_usd=1700.0),
            BudgetBreakdown(category="Contingency (10%)", amount_usd=400.0),
        ],
    )
    timeline = [
        TimelinePhase(week=1, phase="Setup", tasks=["Define experimental groups and controls"], milestone="Protocol locked", depends_on=[]),
        TimelinePhase(week=2, phase="Setup", tasks=["Procure biological materials and reagents"], milestone="Materials in hand", depends_on=["Define experimental groups and controls"]),
        TimelinePhase(week=3, phase="Execution", tasks=["Pilot run (n=3) to lock parameters"], milestone="Pilot complete", depends_on=["Procure biological materials and reagents"]),
        TimelinePhase(week=5, phase="Execution", tasks=["Main experimental cohort"], milestone="Cohort complete", depends_on=["Pilot run (n=3) to lock parameters"]),
        TimelinePhase(week=6, phase="Analysis", tasks=["Primary endpoint measurement", "Statistical analysis & reporting"], milestone="Final results", depends_on=["Main experimental cohort"]),
    ]
    validation = Validation(
        primary_metric="Primary endpoint named in hypothesis",
        success_threshold="Threshold stated in hypothesis",
        control_condition="Vehicle / standard-of-care comparator",
        statistical_test="Pre-registered test (e.g., two-sided t-test or Mann-Whitney U)",
        sample_size="Powered for the stated effect size",
        failure_criteria="Effect not significant OR outside CI",
        reporting_standard="ARRIVE / CONSORT (as applicable)",
    )
    return ExperimentPlanResponse(
        protocol=protocol, reagents=reagents, budget=budget,
        timeline=timeline, validation=validation,
    )


def get_demo_plan_response(hypothesis: str = "") -> ExperimentPlanResponse:
    """Schema-correct fallback plan used when Groq is unreachable / rate-limited.

    Strategy:
      1. Try to match a cached high-quality template (CRISPR / microbiome /
         cryopreservation) when keywords align.
      2. Detect compute / ML / signal-processing hypotheses and route them to
         a compute-skeleton plan instead of any wet-lab cache.
      3. Otherwise build a generic but hypothesis-aware skeleton.

    Every branch surfaces _DEMO_NOTE in `budget.currency_note` so the UI
    can warn the user that this is cached, not freshly generated.
    """
    text = (hypothesis or "").lower()

    # 1. Compute / ML hypotheses MUST never get a wet-lab template — that
    #    was the bug the user reported.
    if _is_compute_or_ml_hypothesis(text):
        return _build_skeleton_plan_from_hypothesis(hypothesis)

    # 2. Topic-matched wet-lab cached templates (only when the keyword
    #    overlap is unambiguous — narrower than before).
    if any(t in text for t in ("crispr", "cas9", "sgrna", "guide rna", "gene knockout", "gene knock-out", "ko cell line", "homologous recombination")):
        return _demo_crispr_plan()
    if any(t in text for t in ("microbiome", "probiotic", "lactobacillus", "bifidobacterium", "fecal", "gut bacteria", "intestinal permeability", "germ-free mice", "germ free mice")):
        return _demo_microbiome_plan()
    if any(t in text for t in ("cryoprotectant", "cryopreservation", "trehalose", "post-thaw", "post thaw", "vitrification", "freezing medium", "viability after freezing")):
        return _demo_cryopreservation_plan()

    # 3. Anything else gets a hypothesis-aware skeleton, never the
    #    cryopreservation default.
    return _build_skeleton_plan_from_hypothesis(hypothesis)


def _safe_load_feedback(feedback_file: str) -> List[dict]:
    if not os.path.exists(feedback_file):
        return []
    try:
        with open(feedback_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning(f"Could not read feedback store: {exc}")
        return []


def _build_protocol(plan_data: dict) -> List[ProtocolStep]:
    items = plan_data.get("protocol") or []
    if not isinstance(items, list):
        return []
    out: List[ProtocolStep] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        out.append(
            ProtocolStep(
                step=_coerce_int(raw.get("step", idx), default=idx),
                title=_coerce_str(raw.get("title", f"Step {idx}")),
                description=_coerce_str(raw.get("description", "")),
                duration=_coerce_str(raw.get("duration", "")),
                safety_note=_coerce_str(raw.get("safety_note", "")),
                source=_coerce_str(raw.get("source", "")),
            )
        )
    return out


def _build_reagents(plan_data: dict) -> List[Reagent]:
    items = plan_data.get("reagents") or []
    if not isinstance(items, list):
        return []
    out: List[Reagent] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        quantity = _coerce_float(raw.get("quantity"))
        unit_price = _coerce_float(raw.get("unit_price_usd"))
        total_cost = _coerce_float(raw.get("total_cost_usd"))
        if total_cost == 0 and quantity and unit_price:
            total_cost = round(quantity * unit_price, 2)
        out.append(
            Reagent(
                name=_coerce_str(raw.get("name", "")),
                quantity=quantity,
                unit=_coerce_str(raw.get("unit", "")),
                concentration=_coerce_str(raw.get("concentration", "N/A")) or "N/A",
                supplier=_coerce_str(raw.get("supplier", "")),
                catalog_number=_coerce_str(raw.get("catalog_number", "")),
                unit_price_usd=unit_price,
                total_cost_usd=total_cost,
                notes=_coerce_str(raw.get("notes", "")),
            )
        )
    return out


def _build_budget(plan_data: dict, reagents: List[Reagent]) -> Budget:
    raw = plan_data.get("budget") or {}
    if not isinstance(raw, dict):
        raw = {}
    breakdown_raw = raw.get("breakdown") or []
    if not isinstance(breakdown_raw, list):
        breakdown_raw = []
    breakdown = [
        BudgetBreakdown(
            category=_coerce_str(b.get("category", "Other")) or "Other",
            amount_usd=_coerce_float(b.get("amount_usd")),
        )
        for b in breakdown_raw
        if isinstance(b, dict)
    ]
    breakdown_sum = round(sum(b.amount_usd for b in breakdown), 2) if breakdown else 0.0
    total = _coerce_float(raw.get("total_usd"))
    reagent_total = round(sum(r.total_cost_usd for r in reagents), 2) if reagents else 0.0

    # If the LLM returned a breakdown of all-zero or near-zero amounts (the
    # 8B fallback model occasionally does this), synthesise a sensible
    # breakdown from the reagent line-items so the UI is never blank.
    if (not breakdown or breakdown_sum <= 0.0) and total > 0.0:
        synth: List[BudgetBreakdown] = []
        if reagent_total > 0.0:
            synth.append(BudgetBreakdown(category="Reagents & Consumables", amount_usd=reagent_total))
            remaining = max(round(total - reagent_total, 2), 0.0)
            if remaining > 0.0:
                # Split the rest 60/30/10 across the standard categories so the
                # pie-chart-style visual still tells a coherent story.
                synth.append(BudgetBreakdown(category="Equipment & Rental", amount_usd=round(remaining * 0.6, 2)))
                synth.append(BudgetBreakdown(category="Labour (estimated)", amount_usd=round(remaining * 0.3, 2)))
                synth.append(BudgetBreakdown(category="Contingency (10%)", amount_usd=round(remaining * 0.1, 2)))
        else:
            synth.append(BudgetBreakdown(category="Reagents & Consumables", amount_usd=round(total * 0.45, 2)))
            synth.append(BudgetBreakdown(category="Equipment & Rental", amount_usd=round(total * 0.30, 2)))
            synth.append(BudgetBreakdown(category="Labour (estimated)", amount_usd=round(total * 0.20, 2)))
            synth.append(BudgetBreakdown(category="Contingency (10%)", amount_usd=round(total * 0.05, 2)))
        breakdown = synth
        breakdown_sum = round(sum(b.amount_usd for b in breakdown), 2)

    # Reconcile total_usd with the breakdown so the UI never shows
    # a contradictory headline number.
    if breakdown_sum > 0 and len(breakdown) >= 3:
        if total <= 0 or abs(total - breakdown_sum) / max(breakdown_sum, 1.0) > 0.05:
            total = breakdown_sum
    elif total <= 0 and breakdown_sum > 0:
        total = breakdown_sum
    elif total <= 0 and reagent_total > 0:
        total = reagent_total

    return Budget(
        total_usd=total,
        currency_note=_coerce_str(raw.get("currency_note", "All prices in USD")) or "All prices in USD",
        breakdown=breakdown,
    )


def _build_timeline(plan_data: dict) -> List[TimelinePhase]:
    items = plan_data.get("timeline") or []
    if not isinstance(items, list):
        return []
    out: List[TimelinePhase] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        week_value = raw.get("week")
        week = _coerce_int(week_value, default=idx) if week_value is not None else idx
        if week < 1:
            week = idx
        depends_on_raw = raw.get("depends_on")
        if isinstance(depends_on_raw, list):
            depends_on = [d for d in depends_on_raw if d not in (None, "")]
        elif depends_on_raw in (None, ""):
            depends_on = []
        else:
            depends_on = [depends_on_raw]
        out.append(
            TimelinePhase(
                week=week,
                phase=_coerce_str(raw.get("phase", "Phase")) or "Phase",
                tasks=_coerce_str_list(raw.get("tasks") or raw.get("description")),
                milestone=_coerce_str(raw.get("milestone", "")),
                depends_on=depends_on,
                start_day=_coerce_int(raw.get("start_day")) if raw.get("start_day") is not None else None,
                duration_days=_coerce_int(raw.get("duration_days")) if raw.get("duration_days") is not None else None,
                description=_coerce_str(raw.get("description", "")) or None,
            )
        )
    return out


def _build_validation(plan_data: dict) -> Validation:
    raw = plan_data.get("validation") or {}
    if not isinstance(raw, dict):
        raw = {}
    # Tolerate older / drifted keys.
    primary_metric = raw.get("primary_metric") or raw.get("metric") or raw.get("success_criteria")
    success_threshold = raw.get("success_threshold") or raw.get("threshold") or raw.get("success_criteria")
    return Validation(
        primary_metric=_coerce_str(primary_metric),
        success_threshold=_coerce_str(success_threshold),
        control_condition=_coerce_str(raw.get("control_condition", "")),
        statistical_test=_coerce_str(raw.get("statistical_test", "")),
        sample_size=_coerce_str(raw.get("sample_size", "")),
        failure_criteria=_coerce_str(raw.get("failure_criteria", "")),
        reporting_standard=_coerce_str(raw.get("reporting_standard", "")),
    )


def _assemble_plan(plan_data: dict) -> ExperimentPlanResponse:
    if not isinstance(plan_data, dict):
        plan_data = {}
    reagents = _build_reagents(plan_data)
    return ExperimentPlanResponse(
        protocol=_build_protocol(plan_data),
        reagents=reagents,
        budget=_build_budget(plan_data, reagents),
        timeline=_build_timeline(plan_data),
        validation=_build_validation(plan_data),
    )


# ============================================================================
# Routes
# ============================================================================


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": GENERATION_MODEL}


@app.post("/api/literature-qc", response_model=LiteratureQCResponse)
async def literature_qc(input_data: HypothesisInput):
    """Check whether a similar experiment exists in the literature."""
    try:
        hypothesis = (input_data.hypothesis or "").strip()
        if len(hypothesis) < 20:
            raise HTTPException(
                status_code=400,
                detail="Please enter a complete scientific hypothesis (at least 20 characters).",
            )

        result = await run_literature_qc(hypothesis)

        if "error" in result and not result.get("references"):
            raise HTTPException(status_code=502, detail=result["error"])

        references = []
        for ref in result.get("references", []) or []:
            try:
                title = _coerce_str(ref.get("title")).strip() or "Untitled"
                authors = _coerce_str(ref.get("authors")).strip() or "Unknown authors"
                references.append(
                    ReferencePaper(
                        title=title[:300],
                        authors=authors,
                        year=_coerce_int(ref.get("year")),
                        url=_coerce_str(ref.get("url", "")),
                        source=_coerce_str(ref.get("source", "")) or None,
                    )
                )
            except Exception as exc:
                logger.warning(f"Skipping malformed reference: {exc}")

        return LiteratureQCResponse(
            signal=result.get("signal", "not_found"),
            explanation=_coerce_str(result.get("explanation", "")),
            references=references,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("literature_qc failed")
        raise HTTPException(status_code=500, detail=str(e))


class GeneratePlanInput(BaseModel):
    hypothesis: str
    feedback_context: Optional[List[dict]] = None


@app.post("/api/generate-plan", response_model=ExperimentPlanResponse)
async def generate_plan(input_data: GeneratePlanInput):
    """Generate a complete experiment plan, with optional learning-loop feedback."""
    try:
        hypothesis = (input_data.hypothesis or "").strip()
        if len(hypothesis) < 20:
            raise HTTPException(
                status_code=400,
                detail="Please enter a complete scientific hypothesis (at least 20 characters).",
            )

        feedback_file = os.path.join(os.path.dirname(__file__), "feedback_store.json")
        feedback_list = _safe_load_feedback(feedback_file)

        # Allow per-request feedback override.
        if input_data.feedback_context:
            feedback_list = list(feedback_list) + list(input_data.feedback_context)

        user_prompt = build_prompt_with_feedback(hypothesis, feedback_list)

        logger.info(f"Generating plan for: {hypothesis[:80]}...")

        response_text = ""
        try:
            response_text, model_used = _groq_chat_with_fallback(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=8000,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            error_str = str(exc)
            logger.error(f"Groq API error (all models): {error_str}")
            # If every model in the chain failed for retryable reasons (rate-limit,
            # JSON validation, decommissioned, 5xx), surface a topic-matched demo
            # plan so the user always sees *something* relevant.
            if _is_retryable_groq_error(exc):
                logger.info("All Groq models exhausted; returning topic-matched demo plan.")
                return get_demo_plan_response(hypothesis)
            raise HTTPException(status_code=502, detail=f"LLM provider error: {error_str}")

        cleaned = _sanitise_json_text(response_text)

        try:
            plan_data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(f"First JSON parse failed: {exc}. Attempting repair.")
            try:
                repaired_text, _ = _groq_chat_with_fallback(
                    messages=[
                        {
                            "role": "system",
                            "content": "You repair invalid JSON. Return ONLY valid JSON, nothing else.",
                        },
                        {"role": "user", "content": cleaned[:6000]},
                    ],
                    max_tokens=6000,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                repaired = _sanitise_json_text(repaired_text)
                plan_data = json.loads(repaired)
            except Exception as repair_exc:
                logger.error(f"JSON repair failed: {repair_exc}. Returning demo plan.")
                return get_demo_plan_response(hypothesis)

        try:
            return _assemble_plan(plan_data)
        except Exception as exc:
            logger.error(f"Plan assembly failed: {exc}. Returning demo plan.")
            return get_demo_plan_response(hypothesis)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_plan failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/save-feedback", response_model=SaveFeedbackResponse)
async def save_feedback(input_data: SaveFeedbackInput):
    """Persist scientist feedback so future plans can reuse it."""
    try:
        feedback_file = os.path.join(os.path.dirname(__file__), "feedback_store.json")
        feedback_list = _safe_load_feedback(feedback_file)

        feedback_list.append(
            {
                "hypothesis": input_data.hypothesis,
                "experiment_type": (input_data.experiment_type or "").strip().lower(),
                "corrections": input_data.corrections or {},
            }
        )

        with open(feedback_file, "w", encoding="utf-8") as fh:
            json.dump(feedback_list, fh, indent=2)

        logger.info(
            f"Feedback saved (experiment_type={input_data.experiment_type!r}, total entries={len(feedback_list)})"
        )
        return SaveFeedbackResponse(saved=True)

    except Exception as e:
        logger.exception("save_feedback failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Startup
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    # Hot-reload is OFF by default so production hosts (Render, Fly, etc.) stay
    # stable. For local dev set RELOAD=1 (or ENV=development) to re-enable it.
    env = os.getenv("ENV", "development").lower()
    reload_flag = os.getenv("RELOAD", "1" if env == "development" else "0") == "1"
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload_flag,
    )
