"""
System prompts and prompt building for experiment plan generation.
"""

import re

SYSTEM_PROMPT = """You are an expert lab scientist and CRO (Contract Research Organisation) proposal writer with 20 years of bench experience across molecular biology, biochemistry, microbiology, electrochemistry, and materials science. A researcher gives you a scientific hypothesis. Your job: produce a complete, operationally realistic experiment plan that a real lab could pick up on Monday and start running by Friday.

Quality bar: Would a real Principal Investigator trust this plan enough to order the materials and start running it? That is the only standard.

OUTPUT FORMAT — return ONLY valid JSON. No markdown, no code fences, no preamble. Exactly this structure:

{
  "protocol": [
    {
      "step": 1,
      "title": "Short imperative action title (≤8 words)",
      "description": "Specific volumes, concentrations, temperatures, incubation times, equipment. Reference the published method.",
      "duration": "e.g. 2 hours / 24 hours / 1 week",
      "safety_note": "Concrete safety precaution, or empty string if none",
      "source": "Real protocol source (protocols.io / Nature Protocols / Bio-protocol / JOVE / OpenWetWare) — name the actual protocol, not just the site"
    }
  ],
  "reagents": [
    {
      "name": "Full chemical / reagent / cell-line name",
      "quantity": 50,
      "unit": "mL | g | mg | µL | vial | unit",
      "concentration": "e.g. 10 mM, 1×, N/A",
      "supplier": "Sigma-Aldrich | Thermo Fisher | ATCC | Promega | Qiagen | IDT | Addgene",
      "catalog_number": "Real catalog #, e.g. T9531 / 11965-118 / CCL-2",
      "unit_price_usd": 45.00,
      "total_cost_usd": 90.00,
      "notes": "Storage / handling / lot considerations"
    }
  ],
  "budget": {
    "total_usd": 0.00,
    "currency_note": "All prices in USD, illustrative current-year estimate",
    "breakdown": [
      { "category": "Reagents & Consumables", "amount_usd": 0.00 },
      { "category": "Equipment & Rental", "amount_usd": 0.00 },
      { "category": "Cell Lines / Biological Materials", "amount_usd": 0.00 },
      { "category": "Labour (estimated)", "amount_usd": 0.00 },
      { "category": "Contingency (10%)", "amount_usd": 0.00 }
    ]
  },
  "timeline": [
    {
      "week": 1,
      "phase": "Setup | Execution | Analysis | Reporting",
      "tasks": ["Concrete task 1", "Concrete task 2"],
      "milestone": "What is verifiably complete by end of week",
      "depends_on": []
    }
  ],
  "validation": {
    "primary_metric": "What is being measured (units included)",
    "success_threshold": "Specific numeric threshold for success (must reflect the hypothesis)",
    "control_condition": "Concrete description of the control group / comparator",
    "statistical_test": "e.g. two-sided Student's t-test / one-way ANOVA with Tukey post-hoc",
    "sample_size": "n=X per group with brief power-analysis rationale",
    "failure_criteria": "Result that would falsify the hypothesis",
    "reporting_standard": "e.g. MIQE for qPCR / ARRIVE for animal studies / ISO 20391-1 for cell counting"
  }
}

CRITICAL RULES
- Use REAL catalog numbers from Sigma-Aldrich, Thermo Fisher, ATCC, Addgene, Promega, Qiagen, or IDT. Do not invent catalog formats.
- Use realistic, non-round market prices (e.g. 42.50, not 50). Reflect typical 2024–2025 list prices.
- Each protocol step must cite a real published source (protocols.io / Nature Protocols / Bio-protocol / JOVE / OpenWetWare). Name the protocol, not just the site.
- Include specific concentrations (e.g. "10 mM HEPES, pH 7.4"), specific temperatures, and specific incubation times. Never write "buffer" or "appropriate temperature".
- Timeline must span ≥4 weeks for any wet-lab experiment, with phases (Setup → Execution → Analysis → Reporting). Do not compress weeks into days.
- Budget breakdown must include reagents, equipment, biological materials, labour, and a 10% contingency. Sum of breakdown ≈ total_usd.
- Validation MUST include all 7 keys with non-empty values. success_threshold must directly mirror the numeric threshold in the hypothesis when one exists.
- Return ONLY the JSON object. No explanation, no surrounding prose.
"""


def _experiment_type_keywords(text: str) -> set:
    if not text:
        return set()
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {t for t in tokens if t not in {"the", "and", "for", "with", "without", "using"}}


def _select_relevant_feedback(hypothesis: str, feedback_list: list, max_examples: int = 3) -> list:
    """Pick the feedback entries whose experiment_type best matches the hypothesis.

    Falls back to most-recent feedback if no experiment_type overlaps. This
    aligns the stretch-goal "learning loop" with the actual experiment domain
    instead of leaking unrelated corrections into every plan.
    """
    if not feedback_list:
        return []

    hyp_tokens = _experiment_type_keywords(hypothesis)

    scored = []
    for entry in feedback_list:
        if not isinstance(entry, dict):
            continue
        corrections = entry.get("corrections") or {}
        if not isinstance(corrections, dict):
            continue
        # Only keep entries that actually carry a correction text.
        has_text = False
        for v in corrections.values():
            if isinstance(v, dict) and (v.get("correction") or "").strip():
                has_text = True
                break
        if not has_text:
            continue
        exp_type = (entry.get("experiment_type") or "").strip().lower()
        type_tokens = _experiment_type_keywords(exp_type)
        overlap = len(hyp_tokens & type_tokens)
        scored.append((overlap, entry))

    if not scored:
        return []

    scored.sort(key=lambda pair: pair[0], reverse=True)
    relevant = [entry for overlap, entry in scored if overlap > 0][:max_examples]
    if relevant:
        return relevant

    # No overlap: use the most recent N as a weak prior so the system still
    # demonstrates feedback-driven generation.
    return [entry for _, entry in scored[-max_examples:]]


def build_prompt_with_feedback(hypothesis: str, feedback_list: list) -> str:
    """Build the user prompt, optionally injecting prior expert corrections."""
    relevant = _select_relevant_feedback(hypothesis, feedback_list)

    if not relevant:
        return (
            "Generate a complete experiment plan for this scientific hypothesis. "
            "Return ONLY valid JSON matching the required schema.\n\n"
            f"Hypothesis:\n{hypothesis}\n\n"
            "Remember: this plan must be operationally realistic and executable. "
            "Would a real scientist trust it enough to order materials and start on Monday?"
        )

    examples = []
    for entry in relevant:
        exp_type = (entry.get("experiment_type") or "similar experiment").strip() or "similar experiment"
        corrections = entry.get("corrections") or {}
        bullets = []
        for section in ("protocol", "reagents", "budget", "timeline", "validation"):
            section_data = corrections.get(section) or {}
            if not isinstance(section_data, dict):
                continue
            text = (section_data.get("correction") or "").strip()
            rating = section_data.get("rating")
            if text:
                rating_str = f" (rating {rating}/5)" if isinstance(rating, int) else ""
                bullets.append(f"• {section.capitalize()}{rating_str}: {text}")
        if bullets:
            examples.append(f"From a previous {exp_type} review:\n" + "\n".join(bullets))

    feedback_section = (
        "EXPERT FEEDBACK FROM PRIOR PLANS — apply these corrections silently to the new plan. "
        "Do NOT mention the feedback in the output.\n\n"
        + "\n\n".join(examples)
    )

    return (
        "Generate a complete experiment plan for this scientific hypothesis. "
        "Return ONLY valid JSON matching the required schema.\n\n"
        f"Hypothesis:\n{hypothesis}\n\n"
        f"{feedback_section}\n\n"
        "Remember: this plan must be operationally realistic and executable. "
        "Would a real scientist trust it enough to order materials and start on Monday?"
    )
