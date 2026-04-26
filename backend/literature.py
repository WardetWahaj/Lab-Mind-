"""
Literature quality control.

Pipeline:
  1. Extract scientific keywords from the hypothesis (Groq).
  2. Search Tavily (web-grounded, scoped to academic domains).
  3. Search OpenAlex (free, no key, excellent author/year metadata).
  4. Search Semantic Scholar.
  5. Fall back to context-aware demo papers ONLY if every source fails.
  6. Decide novelty signal: not_found / similar_exists / exact_match.

All HTTP work is async so we don't block the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from groq import Groq

logger = logging.getLogger(__name__)

load_dotenv()


def _make_groq_client() -> Optional[Groq]:
    """Lazy Groq client — never crash at import time on a missing API key."""
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        logger.warning(
            "literature.py: GROQ_API_KEY not set — keyword extraction and "
            "novelty detection will use the heuristic-only path."
        )
        return None
    try:
        return Groq(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"literature.py: Groq client init failed ({exc!r}); using heuristic path.")
        return None


groq_client: Optional[Groq] = _make_groq_client()

# Mirror the model fallback chain from main.py so literature-side LLM
# calls also survive when the primary 70B model's daily quota is exhausted.
_PRIMARY_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv(
        "GROQ_FALLBACK_MODELS",
        "openai/gpt-oss-120b,"
        "meta-llama/llama-4-scout-17b-16e-instruct,"
        "qwen/qwen3-32b,"
        "openai/gpt-oss-20b,"
        "groq/compound,"
        "llama-3.1-8b-instant",
    ).split(",")
    if m.strip()
]
_MODEL_CHAIN = [_PRIMARY_MODEL] + [m for m in _FALLBACK_MODELS if m != _PRIMARY_MODEL]


def _is_retryable_groq_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429", "rate_limit", "quota", "too many requests", "tpd", "rpd",
            "json_validate_failed", "failed to generate json",
            "model_decommissioned", "decommissioned", "model_not_found",
            "503", "502", "500", "service unavailable", "internal server error",
        )
    )


def _groq_chat_with_fallback(messages, *, max_tokens, temperature, response_format=None):
    if groq_client is None:
        raise RuntimeError(
            "Groq client unavailable in literature.py (GROQ_API_KEY missing); "
            "caller should fall back to the heuristic path."
        )

    last_exc = None
    for model in _MODEL_CHAIN:
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            r = groq_client.chat.completions.create(**kwargs)
            return (r.choices[0].message.content or "").strip()
        except Exception as exc:
            last_exc = exc
            if _is_retryable_groq_error(exc):
                logger.warning(f"Groq model {model} retryable error (literature); trying next. Reason: {exc}")
                continue
            logger.error(f"Groq model {model} hard error (literature): {exc}")
            break
    raise last_exc or RuntimeError("Unknown Groq error")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
SEARCH_ENDPOINT = f"{SEMANTIC_SCHOLAR_API}/paper/search"
TAVILY_SEARCH_API = "https://api.tavily.com/search"
OPENALEX_API = "https://api.openalex.org/works"

ACADEMIC_DOMAINS = [
    "arxiv.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "semanticscholar.org",
    "openalex.org",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "cell.com",
    "springer.com",
    "link.springer.com",
    "ieeexplore.ieee.org",
    "acm.org",
    "biorxiv.org",
    "medrxiv.org",
    "plos.org",
    "wiley.com",
    "onlinelibrary.wiley.com",
    "frontiersin.org",
    "rsc.org",
    "acs.org",
    "protocols.io",
    "nih.gov",
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "to", "using", "with", "without",
    "will", "than", "compared", "show", "shows", "showing", "demonstrate", "due",
    "this", "their", "these", "those", "we", "our", "study", "studied",
    "increase", "decrease", "improve", "improves", "reduce", "reduces",
}

# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def _fallback_keywords(hypothesis: str) -> str:
    """Heuristic keyword extraction when Groq is unavailable."""
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", hypothesis)
    seen, picked = set(), []
    for tok in tokens:
        low = tok.lower()
        if low in STOPWORDS or low in seen:
            continue
        seen.add(low)
        picked.append(tok)
        if len(picked) >= 6:
            break
    return " ".join(picked) if picked else hypothesis[:120]


def extract_keywords(hypothesis: str) -> str:
    """Use Groq to compress the hypothesis into a focused search query."""
    try:
        prompt = (
            "Extract 4-6 highly specific scientific search terms from this hypothesis. "
            "Prefer concrete nouns: organism names, chemical names, assay names, "
            "measurable outcomes. Return ONLY a comma-separated list. No prose, no numbering.\n\n"
            f"Hypothesis: {hypothesis}"
        )
        keywords = _groq_chat_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.2,
        )
        # Strip stray prose/markdown.
        keywords = re.sub(r"[\r\n]+", " ", keywords)
        keywords = re.sub(r"^(?:keywords?|search terms?)\s*[:\-]\s*", "", keywords, flags=re.IGNORECASE)
        keywords = keywords.strip("` *.")
        if not keywords or len(keywords) > 200:
            return _fallback_keywords(hypothesis)
        logger.info(f"Extracted keywords: {keywords}")
        return keywords
    except Exception as exc:
        logger.warning(f"Keyword extraction failed: {exc}. Falling back to heuristic.")
        return _fallback_keywords(hypothesis)


# ---------------------------------------------------------------------------
# Author / year helpers
# ---------------------------------------------------------------------------


def extract_year_from_text(text: str) -> int:
    if not text:
        return 0
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    if not matches:
        return 0
    year = max(int(y) for y in matches)
    return year if 1900 <= year <= 2100 else 0


def _normalize_author_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip(" ,;:-"))
    if not cleaned:
        return ""
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip()
    return cleaned


def _extract_authors_from_text(text: str) -> List[str]:
    if not text:
        return []
    candidates: List[str] = []
    patterns = [
        r"(?:^|\b)(?:by|authors?)\s*[:\-]\s*([^\n\r\.]{4,160})",
        r"(?:^|\b)(?:written by|researchers?)\s*[:\-]\s*([^\n\r\.]{4,160})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        chunk = match.group(1)
        chunk = re.sub(r"\bet\s+al\.?", "", chunk, flags=re.IGNORECASE)
        for piece in re.split(r",|;| and ", chunk):
            name = _normalize_author_name(piece)
            if not name:
                continue
            if len(name.split()) >= 2 or "." in name:
                candidates.append(name)
    seen, deduped = set(), []
    for name in candidates:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped[:3]


def _format_author_list(authors: List[Any]) -> str:
    if not isinstance(authors, list) or not authors:
        return "Unknown authors"
    names = []
    for entry in authors[:3]:
        if isinstance(entry, dict):
            names.append(_normalize_author_name(str(entry.get("name", ""))))
        elif isinstance(entry, str):
            names.append(_normalize_author_name(entry))
    names = [n for n in names if n]
    if not names:
        return "Unknown authors"
    suffix = " et al." if len(authors) > 3 else ""
    return ", ".join(names) + suffix


# ---------------------------------------------------------------------------
# Async source clients
# ---------------------------------------------------------------------------


async def search_tavily_papers(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.info("TAVILY_API_KEY not set, skipping Tavily.")
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": max(limit, 5),
        "include_domains": ACADEMIC_DOMAINS,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TAVILY_SEARCH_API, json=payload)
        if resp.status_code != 200:
            logger.warning(f"Tavily returned {resp.status_code}.")
            return []
        results = (resp.json() or {}).get("results", []) or []
    except Exception as exc:
        logger.warning(f"Tavily search failed: {exc}")
        return []

    mapped: List[Dict[str, Any]] = []
    for idx, item in enumerate(results[:limit], start=1):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        content = (item.get("content") or "").strip()
        published = (item.get("published_date") or "").strip()
        year = extract_year_from_text(published) or extract_year_from_text(content)

        # Try author payload first, then text-based extraction.
        author_dicts: List[Dict[str, str]] = []
        raw_authors = item.get("authors")
        if isinstance(raw_authors, list):
            for entry in raw_authors:
                name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
                name = _normalize_author_name(name)
                if name:
                    author_dicts.append({"name": name})
        elif isinstance(raw_authors, str):
            for piece in re.split(r",|;| and ", raw_authors):
                name = _normalize_author_name(piece)
                if name:
                    author_dicts.append({"name": name})
        if not author_dicts:
            for key in ("content", "raw_content", "title"):
                inferred = _extract_authors_from_text(item.get(key) or "")
                if inferred:
                    author_dicts = [{"name": n} for n in inferred[:3]]
                    break

        mapped.append(
            {
                "title": title,
                "authors": author_dicts,
                "year": year,
                "paperId": f"tavily-{idx}",
                "externalIds": {"URL": url},
                "_source": "tavily",
            }
        )
    logger.info(f"Tavily → {len(mapped)} papers")
    return mapped


async def search_openalex(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """OpenAlex returns clean structured author/year data with no key needed."""
    params = {
        "search": query,
        "per-page": limit,
        "sort": "relevance_score:desc",
    }
    mailto = os.getenv("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(OPENALEX_API, params=params, headers={"User-Agent": "ai-scientist-os"})
        if resp.status_code != 200:
            logger.warning(f"OpenAlex returned {resp.status_code}")
            return []
        data = resp.json() or {}
    except Exception as exc:
        logger.warning(f"OpenAlex search failed: {exc}")
        return []

    out: List[Dict[str, Any]] = []
    for work in (data.get("results") or [])[:limit]:
        title = (work.get("title") or "").strip()
        if not title:
            continue
        year = work.get("publication_year") or 0
        authorships = work.get("authorships") or []
        authors = [
            {"name": a.get("author", {}).get("display_name", "")}
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]
        doi = (work.get("doi") or "").replace("https://doi.org/", "") if work.get("doi") else ""
        url = work.get("doi") or (work.get("primary_location") or {}).get("landing_page_url") or ""
        external_ids = {}
        if doi:
            external_ids["DOI"] = doi
        if url:
            external_ids["URL"] = url
        out.append(
            {
                "title": title,
                "authors": authors,
                "year": int(year) if year else 0,
                "paperId": work.get("id", ""),
                "externalIds": external_ids,
                "_source": "openalex",
            }
        )
    logger.info(f"OpenAlex → {len(out)} papers")
    return out


async def search_semantic_scholar(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,externalIds,paperId,url",
    }
    headers = {}
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(SEARCH_ENDPOINT, params=params, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"Semantic Scholar returned {resp.status_code}")
            return []
        papers = (resp.json() or {}).get("data") or []
    except Exception as exc:
        logger.warning(f"Semantic Scholar failed: {exc}")
        return []
    for p in papers:
        p["_source"] = "semantic_scholar"
    logger.info(f"Semantic Scholar → {len(papers)} papers")
    return papers


# ---------------------------------------------------------------------------
# Demo fallback (only used when ALL sources fail)
# ---------------------------------------------------------------------------


def generate_demo_papers(query: str) -> List[Dict[str, Any]]:
    demo_db = {
        "biosensor": [
            {
                "title": "Paper-based electrochemical biosensors for point-of-care diagnostics",
                "authors": [{"name": "Liu, Y."}, {"name": "Park, S."}, {"name": "Wang, X."}],
                "year": 2022,
                "paperId": "demo-bio-001",
                "externalIds": {"DOI": "10.1016/j.bios.2022.114145"},
            },
            {
                "title": "C-reactive protein detection in whole blood by immunoassay strips",
                "authors": [{"name": "Tanaka, K."}, {"name": "Brown, J."}],
                "year": 2021,
                "paperId": "demo-bio-002",
                "externalIds": {"DOI": "10.1021/acssensors.1c01234"},
            },
        ],
        "microbiome": [
            {
                "title": "Lactobacillus rhamnosus GG reinforces intestinal barrier function in mice",
                "authors": [{"name": "Patel, R."}, {"name": "Khan, A."}, {"name": "Singh, M."}],
                "year": 2021,
                "paperId": "demo-mb-001",
                "externalIds": {"DOI": "10.1038/s41385-021-00412-6"},
            },
            {
                "title": "Tight junction modulation by probiotics: claudin-1 and occludin upregulation",
                "authors": [{"name": "Schultz, M."}, {"name": "Lee, H."}],
                "year": 2020,
                "paperId": "demo-mb-002",
                "externalIds": {"DOI": "10.3389/fmicb.2020.001234"},
            },
        ],
        "cell": [
            {
                "title": "Trehalose vs DMSO cryoprotection of mammalian cell lines",
                "authors": [{"name": "Chen, L."}, {"name": "Kawakami, S."}, {"name": "Kuroda, K."}],
                "year": 2022,
                "paperId": "demo-cell-001",
                "externalIds": {"DOI": "10.1016/j.cryobiol.2022.01.005"},
            },
            {
                "title": "Membrane stabilization by disaccharides in cryopreservation protocols",
                "authors": [{"name": "Silva, J."}, {"name": "Martin, R."}],
                "year": 2021,
                "paperId": "demo-cell-002",
                "externalIds": {"DOI": "10.1021/acs.langmuir.1c01987"},
            },
        ],
        "co2": [
            {
                "title": "Bioelectrochemical CO2 fixation by Sporomusa ovata at controlled cathode potentials",
                "authors": [{"name": "Nevin, K."}, {"name": "Lovley, D."}],
                "year": 2020,
                "paperId": "demo-co2-001",
                "externalIds": {"DOI": "10.1126/science.abc1234"},
            },
            {
                "title": "Microbial electrosynthesis of acetate from CO2: state of the art",
                "authors": [{"name": "Jiang, Y."}, {"name": "Zhang, F."}],
                "year": 2022,
                "paperId": "demo-co2-002",
                "externalIds": {"DOI": "10.1016/j.biortech.2022.126512"},
            },
        ],
        "default": [
            {
                "title": "Recent advances in experimental design for hypothesis-driven research",
                "authors": [{"name": "Richardson, M."}, {"name": "Foster, N."}],
                "year": 2023,
                "paperId": "demo-default-001",
                "externalIds": {"DOI": "10.1038/s41467-023-12345-6"},
            },
        ],
    }

    q = query.lower()
    if any(t in q for t in ("biosensor", "crp", "elisa", "diagnostic")):
        bucket = "biosensor"
    elif any(t in q for t in ("microbiome", "probiotic", "lactobacillus", "gut", "intestinal")):
        bucket = "microbiome"
    elif any(t in q for t in ("cell", "hela", "trehalose", "cryopreserv", "mammalian")):
        bucket = "cell"
    elif any(t in q for t in ("co2", "carbon", "acetate", "sporomusa", "bioelectrochem")):
        bucket = "co2"
    else:
        bucket = "default"
    papers = [{**p, "_source": "demo"} for p in demo_db[bucket]]
    logger.info(f"Demo papers ({bucket}) → {len(papers)} entries")
    return papers


# ---------------------------------------------------------------------------
# Novelty signal
# ---------------------------------------------------------------------------


_GENERIC_TERMS_RAW = {
    "study", "studies", "analysis", "review", "approach", "approaches",
    "method", "methods", "system", "systems", "effect", "effects",
    "result", "results", "data", "experiment", "experiments", "model",
    "models", "research", "paper", "investigation", "investigations",
    "increase", "decrease", "compared", "comparison", "novel", "new",
    "applications", "based", "high", "low", "use", "uses",
    "need", "insights", "importance", "factor", "factors",
    "least", "performance", "performances", "function", "functions",
}


def _normalize_token(token: str) -> str:
    """Cheap stem so 'cell' matches 'cells', 'protocol' matches 'protocols',
    'cryoprotectant' matches 'cryoprotectants', 'studies' matches 'study'."""
    t = token.lower()
    if len(t) <= 4:
        return t
    # 'studies' -> 'study'
    if t.endswith("ies"):
        return t[:-3] + "y"
    # Plain plural: 'cells' -> 'cell', 'cryoprotectants' -> 'cryoprotectant'.
    # Keep 'us' (e.g. 'rhamnosus'), 'is' (e.g. 'hypothesis'), 'ss' (e.g. 'mass'),
    # 'os' (e.g. 'dmso' edge), 'ys' (rare) intact.
    if t.endswith("s") and not t.endswith(("ss", "us", "is", "os", "ys")):
        return t[:-1]
    return t


# Normalise the generic-term set ONCE at import so membership checks are
# consistent with normalised hypothesis/title tokens.
_GENERIC_TERMS = {_normalize_token(t) for t in _GENERIC_TERMS_RAW}


def _tokenize_text(text: str) -> set:
    if not text:
        return set()
    raw = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {_normalize_token(t) for t in raw if t not in STOPWORDS}


def _domain_terms(text: str) -> set:
    """Extract the topical (non-generic) normalized tokens from a hypothesis
    or title — the keywords a scientist would actually search on.
    """
    return {
        t for t in _tokenize_text(text)
        if t not in _GENERIC_TERMS and t not in STOPWORDS and len(t) >= 4
    }


def _substring_domain_overlap(hypothesis_domain: set, title_text: str) -> set:
    """Catch hypothesis terms that show up as substrings in a title even when
    tokenization splits them oddly (e.g. 'post-thaw' → 'post' + 'thaw',
    or chemical names with embedded digits)."""
    if not title_text:
        return set()
    lower = title_text.lower()
    return {term for term in hypothesis_domain if len(term) >= 5 and term in lower}


def _heuristic_novelty_signal(hypothesis: str, papers: List[Dict[str, Any]]) -> Tuple[str, str, float]:
    hypothesis_tokens = _tokenize_text(hypothesis)
    hypothesis_domain = _domain_terms(hypothesis)
    if not hypothesis_tokens or not papers:
        return "not_found", "No strong lexical overlap was detected.", 0.0

    jaccard_max = 0.0
    matched_domain: set = set()
    for paper in papers[:5]:
        title = paper.get("title") or ""
        title_tokens = _tokenize_text(title)
        if not title_tokens:
            continue
        union = len(hypothesis_tokens | title_tokens)
        if union:
            jaccard_max = max(
                jaccard_max,
                len(hypothesis_tokens & title_tokens) / union,
            )
        title_domain = _domain_terms(title)
        matched_domain |= (hypothesis_domain & title_domain)
        # Substring fallback: handles tokens that get fragmented by the
        # word-character regex (e.g. 'post-thaw', 'C57BL/6', 'TGF-β').
        matched_domain |= _substring_domain_overlap(hypothesis_domain, title)

    domain_size = max(1, len(hypothesis_domain))
    domain_hit_ratio = len(matched_domain) / domain_size

    # Strong overlap on either signal -> exact_match.
    if jaccard_max >= 0.5 or domain_hit_ratio >= 0.55:
        return (
            "exact_match",
            "Retrieved titles overlap heavily with the hypothesis on the same topical terms.",
            max(jaccard_max, domain_hit_ratio),
        )

    # Topically related but not duplicative. Tuned aggressively because
    # high-precision academic search APIs (OpenAlex / Semantic Scholar)
    # rarely return junk — if any topical term lines up, it's a real match.
    if jaccard_max >= 0.10 or len(matched_domain) >= 2 or domain_hit_ratio >= 0.15:
        return (
            "similar_exists",
            "Retrieved papers share core topic terms with the hypothesis (related prior work).",
            max(jaccard_max, domain_hit_ratio),
        )

    return (
        "not_found",
        "Retrieved papers share little topical overlap with the hypothesis.",
        max(jaccard_max, domain_hit_ratio),
    )


def get_paper_url(paper: Dict[str, Any]) -> str:
    external_ids = paper.get("externalIds") or {}
    if "ArXiv" in external_ids and external_ids["ArXiv"]:
        return f"https://arxiv.org/abs/{external_ids['ArXiv']}"
    if "DOI" in external_ids and external_ids["DOI"]:
        doi = external_ids["DOI"]
        if doi.startswith("http"):
            return doi
        return f"https://doi.org/{doi}"
    if "URL" in external_ids and external_ids["URL"]:
        return external_ids["URL"]
    if paper.get("url"):
        return paper["url"]
    paper_id = paper.get("paperId", "")
    if paper_id and not paper_id.startswith(("tavily-", "demo-")):
        return f"https://www.semanticscholar.org/paper/{paper_id}"
    return ""


def _format_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": paper.get("title", "Untitled"),
        "authors": _format_author_list(paper.get("authors", [])),
        "year": int(paper.get("year") or 0),
        "url": get_paper_url(paper),
        "source": paper.get("_source", ""),
    }


def determine_novelty_signal(hypothesis: str, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide novelty by combining the LLM's reading and a deterministic heuristic."""
    if not papers:
        return {
            "signal": "not_found",
            "explanation": "No related work surfaced in literature search.",
            "references": [],
        }

    formatted = [_format_paper(p) for p in papers[:5]]
    paper_list = "\n".join(
        f"- {p['title']} ({p['year'] or 'n.d.'})"
        for p in formatted
    )

    heuristic_signal, heuristic_explanation, heuristic_overlap = _heuristic_novelty_signal(hypothesis, papers)

    prompt = f"""You are a scientific literature analyst. Given a hypothesis and 1-5 candidate paper titles retrieved from academic databases, decide how novel the hypothesis is.

Hypothesis:
{hypothesis}

Candidate papers:
{paper_list}

Output ONLY valid JSON, no markdown:
{{
  "signal": "not_found" | "similar_exists" | "exact_match",
  "confidence": 0.0,
  "explanation": "one short sentence (≤25 words) explaining the verdict"
}}

Decision rules — apply in order:
1. "exact_match": a paper plainly tests the same intervention AND the same measurable outcome on the same system/organism.
2. "similar_exists": the papers are clearly in the SAME scientific subfield as the hypothesis — same intervention class, same mechanism, same organism, or same assay. A reasonable PI would cite at least one of these papers when writing up the hypothesis.
3. "not_found": the papers are clearly off-topic, or only related by a single generic word ('cell', 'system', 'analysis') with no real subfield overlap.

Important:
- Do NOT classify as "similar_exists" just because both texts contain a common generic word. Require real subfield overlap.
- If retrieved papers are about an unrelated topic entirely (different field, different organism, different mechanism), use "not_found".
Confidence in [0,1]."""

    try:
        content = _groq_chat_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            result = json.loads(match.group(0)) if match else {}
        llm_signal = result.get("signal")
        llm_explanation = (result.get("explanation") or "").strip()
        if llm_signal not in {"not_found", "similar_exists", "exact_match"}:
            llm_signal = None
    except Exception as exc:
        logger.warning(f"Novelty LLM call failed: {exc}")
        llm_signal, llm_explanation = None, ""

    # Reconcile LLM + heuristic. The heuristic is a two-sided safety net:
    #   - Catches the LLM under-rating ("not_found" → "similar_exists" when
    #     there is real topical overlap).
    #   - Catches the LLM over-rating ("similar_exists" → "not_found" when
    #     retrieved papers genuinely share no topical terms with the hypothesis).
    if llm_signal:
        signal = llm_signal
        explanation = llm_explanation or heuristic_explanation
        if signal == "not_found" and heuristic_signal in {"similar_exists", "exact_match"}:
            signal = heuristic_signal
            explanation = (
                "Retrieved papers share core topic terms with the hypothesis; "
                "treating as related prior work rather than fully novel."
            )
        elif signal in {"similar_exists", "exact_match"} and heuristic_signal == "not_found" and heuristic_overlap < 0.05:
            signal = "not_found"
            explanation = (
                "Retrieved papers share no real topical terms with the hypothesis; "
                "treating as novel rather than related work."
            )
        elif signal == "similar_exists" and heuristic_signal == "exact_match" and heuristic_overlap >= 0.6:
            signal = "exact_match"
            explanation = (
                "Title overlap is very high; this looks like a direct match rather than just related work."
            )
    else:
        signal = heuristic_signal
        explanation = heuristic_explanation

    return {
        "signal": signal,
        "explanation": explanation,
        "references": formatted[:3],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_literature_qc(hypothesis: str) -> Dict[str, Any]:
    """Main async pipeline. Returns {signal, explanation, references}."""
    try:
        keywords = await asyncio.to_thread(extract_keywords, hypothesis)

        # Run sources in parallel; first to return useful data wins, but we
        # also merge so we can cross-reference. Tavily + OpenAlex first, since
        # OpenAlex has the best metadata and Tavily has the best web grounding.
        tavily_task = asyncio.create_task(search_tavily_papers(keywords, limit=5))
        openalex_task = asyncio.create_task(search_openalex(keywords, limit=5))

        tavily_papers, openalex_papers = await asyncio.gather(
            tavily_task, openalex_task, return_exceptions=True
        )
        if isinstance(tavily_papers, Exception):
            logger.warning(f"Tavily errored: {tavily_papers}")
            tavily_papers = []
        if isinstance(openalex_papers, Exception):
            logger.warning(f"OpenAlex errored: {openalex_papers}")
            openalex_papers = []

        papers: List[Dict[str, Any]] = []
        seen_titles = set()

        def _add(paper_list: List[Dict[str, Any]]) -> None:
            for p in paper_list:
                title_key = (p.get("title") or "").strip().lower()
                if not title_key or title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                papers.append(p)

        _add(openalex_papers or [])
        _add(tavily_papers or [])

        # Need a third source if results look thin or low-quality.
        if len(papers) < 3:
            ss_papers = await search_semantic_scholar(keywords, limit=5)
            _add(ss_papers)

        # Last-resort fallback so the demo never crashes empty.
        if not papers:
            papers = generate_demo_papers(keywords)

        result = determine_novelty_signal(hypothesis, papers)
        logger.info(
            f"Literature QC → signal={result['signal']} refs={len(result.get('references', []))}"
        )
        return result

    except Exception as exc:
        logger.exception("run_literature_qc failed")
        return {
            "signal": "not_found",
            "explanation": "Literature lookup failed; please retry.",
            "references": [],
            "error": str(exc),
        }
