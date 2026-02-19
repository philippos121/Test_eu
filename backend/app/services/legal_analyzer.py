"""
Legal validity and payment ability analyzer.

Uses GPT-4o (with optional Tavily web search) to assess:

1. Legal validity — three structural questions:
   - p_entstanden:        Did the claim arise? (contract formed, obligation triggered)
   - p_not_untergegangen: Is the claim still alive? (no payment, set-off, prescription)
   - p_durchsetzbar:      Is it enforceable here? (jurisdiction, ESCP eligibility)

2. Payment ability — defendant's capacity to pay if judgment is rendered.

Each function runs a multi-turn OpenAI function-calling loop. If TAVILY_API_KEY is
configured, real web searches are performed; otherwise the LLM reasons from its
training knowledge (still valuable for EU member-state law).

Fallback: on any error → neutral probabilities (0.5 / 50.0) so scoring never crashes.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from ..config import get_settings
from ..models import Case

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LegalValidityResult:
    p_entstanden: float = 0.5
    p_entstanden_reasoning: str = ""
    p_not_untergegangen: float = 0.85   # default: no signals of extinguishment
    p_not_untergegangen_reasoning: str = ""
    p_durchsetzbar: float = 0.5
    p_durchsetzbar_reasoning: str = ""
    p_claim_valid_llm: float = 0.5      # product of the three components above
    applicable_law: str = ""
    key_legal_issues: list = field(default_factory=list)
    searches_performed: list = field(default_factory=list)
    error: str = ""


@dataclass
class PaymentAbilityResult:
    ability_score: float = 50.0     # 0–100
    insolvency_risk: str = "unknown"
    reasoning: str = ""
    searches_performed: list = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_LEGAL_VALIDITY_SYSTEM = """\
You are a legal analyst specialising in European civil law and the EU Small Claims
Procedure (ESCP, Regulation EC 861/2007).

Analyse the case facts below and answer three legal questions using the applicable
national law for the defendant's domicile (or the court's jurisdiction if specified).

Rules:
- Assess ONLY what is alleged — missing evidence does NOT lower p_entstanden;
  it lowers provability, which is assessed separately.
- If no signal of extinguishment exists, set p_not_untergegangen ≥ 0.85.
- Use web search to verify jurisdiction-specific limitation periods, statutory
  interest rules, or ESCP eligibility requirements where relevant.

Questions:
1. p_entstanden  (0–1): Did the claim arise?
   Contract claim → contract formed + claimant performed + payment due?
   Statutory claim → all elements of the norm satisfied?

2. p_not_untergegangen  (0–1): Is the claim still alive?
   Signals of extinction: payment, set-off, novation, limitation period expired,
   waiver, insolvency discharge already completed.

3. p_durchsetzbar  (0–1): Is the claim formally enforceable?
   Court has jurisdiction? ESCP applicable (cross-border EU, ≤ 5 000 EUR)?
   No lis pendens / res iudicata bar?

Respond with a single JSON object (no markdown fences, no extra text):
{
  "p_entstanden": <float>,
  "p_entstanden_reasoning": "<≤120 chars>",
  "p_not_untergegangen": <float>,
  "p_not_untergegangen_reasoning": "<≤120 chars>",
  "p_durchsetzbar": <float>,
  "p_durchsetzbar_reasoning": "<≤120 chars>",
  "applicable_law": "<e.g. Austrian ABGB §1062, German BGB §433>",
  "key_legal_issues": ["<issue>"],
  "searches_performed": ["<query used>"]
}
"""

_PAYMENT_ABILITY_SYSTEM = """\
You are a credit-risk analyst assessing a debtor's ability to pay a civil judgment.

Given the debtor profile, estimate the probability (0–100 score) that the debtor
is financially able to satisfy a judgment.

Consider: insolvency register entries, company registration status (active / struck off),
VAT validity, legal person vs. natural person (companies have assets, but also higher
insolvency risk).

Use web search to check public insolvency or company registers if the defendant's
name, country, or registration number is available.

Respond with a single JSON object (no markdown fences, no extra text):
{
  "ability_score": <0–100>,
  "insolvency_risk": "<low|medium|high|unknown>",
  "reasoning": "<≤200 chars>",
  "searches_performed": ["<query>"]
}
"""

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the web for legal information, insolvency registers, or company "
            "registers relevant to this case."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (be specific, include country + legal term)",
                }
            },
            "required": ["query"],
        },
    },
}

# ---------------------------------------------------------------------------
# Web search (Tavily) — graceful degradation if no API key
# ---------------------------------------------------------------------------

async def _tavily_search(query: str) -> str:
    """Perform a real-time web search via Tavily. Returns formatted snippet."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return (
            f"[Web search not available — no TAVILY_API_KEY configured. "
            f"Use your training knowledge to answer: {query}]"
        )
    try:
        import httpx
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        if not results:
            return f"[No results for: {query}]"
        return "\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:300]}"
            for r in results[:3]
        )
    except Exception as exc:
        logger.warning("Tavily search failed for '%s': %s", query, exc)
        return f"[Search error for '{query}': {exc}]"


# ---------------------------------------------------------------------------
# Core LLM call-loop  (max 3 search rounds)
# ---------------------------------------------------------------------------

async def _llm_with_search(system_prompt: str, user_message: str) -> str:
    """
    Run GPT-4o with the search_web tool.
    Returns the final text content of the assistant message.
    At most 3 search rounds to bound latency.
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for _round in range(4):  # 0–2 = search rounds; 3 = final answer (no tools)
        include_tools = _round < 3  # disable tools on last round to force answer
        kwargs = dict(
            model=settings.openai_model,
            messages=messages,
            temperature=0.1,
            max_tokens=800,
        )
        if include_tools:
            kwargs["tools"] = [_SEARCH_TOOL]
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        # Execute tool calls in sequence (usually just one)
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]})

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
                query = args.get("query", "")
            except Exception:
                query = tc.function.arguments

            result = await _tavily_search(query)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return ""  # should not reach here


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_case_description(case: Case, merged_facts: dict) -> str:
    """Build a compact case description string for the LLM prompt."""
    parts = [
        f"Claim amount: {case.claim_amount} {case.claim_currency or 'EUR'}",
        f"Claimant country: {case.claimant_domicile_country or case.claimant_country or '?'}",
        f"Defendant country: {case.defendant_domicile_country or case.defendant_country or '?'}",
        f"Court country: {case.court_country or case.court_member_state or '?'}",
        f"Is cross-border: {case.is_cross_border}",
        f"Defendant is legal person: {case.defendant_is_legal_person}",
    ]
    if case.defendant_name:
        parts.append(f"Defendant name: {case.defendant_name}")
    if case.defendant_id_number:
        parts.append(f"Defendant registration number: {case.defendant_id_number}")
    if case.claim_description:
        parts.append(f"\nClaim description:\n{case.claim_description[:800]}")
    if case.claim_basis:
        parts.append(f"\nLegal basis alleged:\n{case.claim_basis[:400]}")
    if case.additional_information:
        parts.append(f"\nAdditional information:\n{case.additional_information[:400]}")
    if case.applicable_law:
        parts.append(f"\nApplicable law (system assessment): {case.applicable_law}")
    if merged_facts:
        interesting = {
            k: v for k, v in merged_facts.items()
            if v not in (None, False, "")
        }
        if interesting:
            parts.append(f"\nExtracted facts: {json.dumps(interesting, ensure_ascii=False)}")
    return "\n".join(parts)


async def analyze_legal_validity(
    case: Case,
    merged_facts: dict,
) -> LegalValidityResult:
    """
    Ask GPT-4o (with optional web search) to assess legal validity.
    Returns LegalValidityResult; falls back to neutral values on error.
    """
    case_desc = _build_case_description(case, merged_facts)
    user_msg = f"Analyse this case and return the JSON:\n\n{case_desc}"

    try:
        raw = await _llm_with_search(_LEGAL_VALIDITY_SYSTEM, user_msg)
        # Strip accidental markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        p_e = float(data.get("p_entstanden", 0.5))
        p_n = float(data.get("p_not_untergegangen", 0.85))
        p_d = float(data.get("p_durchsetzbar", 0.5))
        p_valid_llm = p_e * p_n * p_d

        return LegalValidityResult(
            p_entstanden=round(max(0.0, min(1.0, p_e)), 4),
            p_entstanden_reasoning=data.get("p_entstanden_reasoning", ""),
            p_not_untergegangen=round(max(0.0, min(1.0, p_n)), 4),
            p_not_untergegangen_reasoning=data.get("p_not_untergegangen_reasoning", ""),
            p_durchsetzbar=round(max(0.0, min(1.0, p_d)), 4),
            p_durchsetzbar_reasoning=data.get("p_durchsetzbar_reasoning", ""),
            p_claim_valid_llm=round(max(0.0, min(1.0, p_valid_llm)), 4),
            applicable_law=data.get("applicable_law", ""),
            key_legal_issues=data.get("key_legal_issues", []),
            searches_performed=data.get("searches_performed", []),
        )

    except Exception as exc:
        logger.error("analyze_legal_validity failed for case %s: %s", case.id, exc)
        return LegalValidityResult(
            p_claim_valid_llm=0.5,
            error=str(exc),
        )


async def analyze_payment_ability(
    case: Case,
    merged_facts: dict,
) -> PaymentAbilityResult:
    """
    Ask GPT-4o (with optional web search) to assess defendant's payment ability.
    Returns PaymentAbilityResult; falls back to 50/unknown on error.
    """
    case_desc = _build_case_description(case, merged_facts)
    user_msg = (
        "Assess the defendant's ability to pay a civil judgment.\n\n"
        f"{case_desc}"
    )

    try:
        raw = await _llm_with_search(_PAYMENT_ABILITY_SYSTEM, user_msg)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        score = float(data.get("ability_score", 50.0))
        return PaymentAbilityResult(
            ability_score=round(max(0.0, min(100.0, score)), 2),
            insolvency_risk=data.get("insolvency_risk", "unknown"),
            reasoning=data.get("reasoning", ""),
            searches_performed=data.get("searches_performed", []),
        )

    except Exception as exc:
        logger.error("analyze_payment_ability failed for case %s: %s", case.id, exc)
        return PaymentAbilityResult(
            ability_score=50.0,
            insolvency_risk="unknown",
            error=str(exc),
        )
