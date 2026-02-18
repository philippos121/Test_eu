"""Pipeline orchestrator — main API for case estimation.

estimate_case():
  1. Determines applicable law
  2. Performs legal research (always, cached OK)
  3. Computes p_recht (with gates)
  4. Computes p_beweis
  5. p_obsiegen = p_recht * p_beweis
  6. If do_external_checks: computes p_eintreibung
  7. p_gesamt = p_obsiegen * p_eintreibung (if available)
  8. Computes EV_betreiber + take_case

update_from_closed_case():
  Updates Bayesian learning parameters from case outcome.
"""
from __future__ import annotations

import logging
from typing import Optional

from .math_utils import clamp
from .models import (
    CaseInput,
    ClosedCaseFeedback,
    CostModelParams,
    EstimateResult,
    EvidenceItem,
    LearningParams,
    RecoveryInput,
)
from .legal_research import (
    determine_applicable_law,
    research_legal_bases,
)
from .merits import compute_p_recht
from .proof import compute_p_beweis
from .recovery import compute_p_eintreibung
from .ev import compute_ev
from .learning import context_key, get_learning_params, update_from_closed_case as _update_learning
from .persistence import PipelineStore
from .search import SearchClient
from .fetch import FetchClient

logger = logging.getLogger(__name__)

# Shared clients (singleton-like for caching)
_search_client: SearchClient | None = None
_fetch_client: FetchClient | None = None
_store: PipelineStore | None = None


def _get_search_client() -> SearchClient:
    global _search_client
    if _search_client is None:
        _search_client = SearchClient()
    return _search_client


def _get_fetch_client() -> FetchClient:
    global _fetch_client
    if _fetch_client is None:
        _fetch_client = FetchClient()
    return _fetch_client


def _get_store() -> PipelineStore:
    global _store
    if _store is None:
        _store = PipelineStore()
    return _store


async def estimate_case(
    case_input: CaseInput,
    evidence_items: list[EvidenceItem] | None = None,
    recovery_input: RecoveryInput | None = None,
    cost_params: CostModelParams | None = None,
    do_external_checks: bool = False,
) -> EstimateResult:
    """Main pipeline: estimate all probabilities for a case.

    Args:
        case_input: Case details and allegations.
        evidence_items: Evidence items for p_beweis.
        recovery_input: Debtor info for p_eintreibung.
        cost_params: Cost model parameters for EV calculation.
        do_external_checks: Whether to perform insolvency/web checks.

    Returns:
        Full EstimateResult with all tiers.
    """
    evidence_items = evidence_items or []
    warnings: list[str] = []
    all_sources = []

    search = _get_search_client()
    fetch = _get_fetch_client()
    store = _get_store()

    # Load learning params
    learning_store = store.load_learning_params()
    is_b2b = not case_input.debtor_is_consumer and not case_input.creditor_is_consumer
    ctx = context_key(
        case_input.claim_type.value,
        case_input.applicable_law_country or case_input.court_country,
        is_b2b,
    )
    learning_params = get_learning_params(ctx, learning_store)

    # ── Step 1: Determine applicable law ──
    applicable_law = determine_applicable_law(case_input)
    if applicable_law.confidence < 0.8:
        warnings.append(
            f"Anwendbares Recht unsicher ({applicable_law.method}): "
            f"{applicable_law.notes}"
        )

    # ── Step 2: Legal research (always) ──
    legal_research = await research_legal_bases(
        case_input, applicable_law, search, fetch
    )
    all_sources.extend(legal_research.sources)
    if legal_research.research_warnings:
        warnings.extend(legal_research.research_warnings)

    # ── Step 3: p_recht ──
    merits = compute_p_recht(case_input, legal_research)
    p_recht = merits.p_recht

    # ── Step 4: p_beweis ──
    proof = compute_p_beweis(case_input, evidence_items, learning_params)
    p_beweis = proof.p_beweis

    # ── Step 5: p_obsiegen ──
    p_obsiegen = clamp(p_recht * p_beweis, 0.0, 1.0)

    # Hard gate override
    if merits.gate.is_hard_exclusion:
        p_obsiegen = 0.0

    # ── Step 6: p_eintreibung (if checks requested) ──
    recovery_result = None
    p_eintreibung = None
    p_gesamt = None

    if recovery_input:
        recovery_result = await compute_p_eintreibung(
            recovery_input,
            case_input.debtor_country,
            do_external_checks=do_external_checks,
            search_client=search,
            fetch_client=fetch,
        )
        p_eintreibung = recovery_result.p_eintreibung
        for sig in recovery_result.signals:
            if sig.source:
                all_sources.append(sig.source)

        if p_eintreibung is not None:
            p_gesamt = clamp(p_obsiegen * p_eintreibung, 0.0, 1.0)
        else:
            warnings.append("p_eintreibung ausstehend — externe Checks nicht durchgeführt.")

    # ── Step 7: EV ──
    ev_result = compute_ev(case_input, p_obsiegen, cost_params)

    # Log prediction
    store.log_prediction(
        case_id=str(case_input.case_id),
        p_obsiegen=round(p_obsiegen, 4),
        p_eintreibung=round(p_eintreibung, 4) if p_eintreibung else None,
        context_key=ctx,
    )

    return EstimateResult(
        case_id=case_input.case_id,
        p_recht=round(p_recht, 4),
        merits=merits,
        p_beweis=round(p_beweis, 4),
        proof=proof,
        p_obsiegen=round(p_obsiegen, 4),
        p_eintreibung=round(p_eintreibung, 4) if p_eintreibung is not None else None,
        recovery=recovery_result,
        p_gesamt=round(p_gesamt, 4) if p_gesamt is not None else None,
        ev=ev_result,
        warnings=warnings,
        sources=all_sources,
        model_version="v3",
    )


async def update_from_closed_case_api(
    case_input: CaseInput,
    evidence_items: list[EvidenceItem],
    feedback: ClosedCaseFeedback,
) -> None:
    """Update learning parameters from a closed case outcome."""
    store = _get_store()
    learning_store = store.load_learning_params()
    _update_learning(case_input, evidence_items, feedback, learning_store)
    store.save_learning_params(learning_store)
