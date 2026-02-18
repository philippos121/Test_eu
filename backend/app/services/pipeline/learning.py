"""Bayesian learning from closed case feedback.

Context-stratified: parameters namespaced by (claim_type, law_country, b2b/b2c).
Hierarchical partial pooling when cell data is small.
Noisy-label handling via reason_confidence weighting.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .math_utils import beta_mean
from .models import (
    CaseInput,
    CaseOutcome,
    ClosedCaseFeedback,
    EvidenceItem,
    EvidenceType,
    LearningParams,
)

logger = logging.getLogger(__name__)

# Default prior pseudocounts for element-level Beta distributions
_DEFAULT_ALPHA = 2.0
_DEFAULT_BETA = 2.0


def context_key(
    claim_type: str,
    law_country: str,
    is_b2b: bool,
) -> str:
    """Build context key for parameter lookup."""
    b2b_label = "b2b" if is_b2b else "b2c"
    return f"{claim_type}:{law_country}:{b2b_label}"


def get_learning_params(
    ctx_key: str,
    store: dict[str, LearningParams] | None = None,
) -> LearningParams:
    """Get learning parameters for a context, with global fallback."""
    if store and ctx_key in store:
        return store[ctx_key]

    # Try partial key (claim_type:*:b2b)
    if store:
        parts = ctx_key.split(":")
        fallback_key = f"{parts[0]}:*:{parts[2]}" if len(parts) == 3 else None
        if fallback_key and fallback_key in store:
            return store[fallback_key]

        # Global fallback
        if "*:*:*" in store:
            return store["*:*:*"]

    return LearningParams(context_key=ctx_key)


def update_from_closed_case(
    case: CaseInput,
    evidence_items: list[EvidenceItem],
    feedback: ClosedCaseFeedback,
    store: dict[str, LearningParams],
) -> None:
    """Update learning parameters from a closed case.

    Two modes:
    A) With reason_label: conditional Beta updates per element
    B) Without reason_label: simple won/lost update on all elements
    """
    is_b2b = not case.debtor_is_consumer and not case.creditor_is_consumer
    ctx = context_key(
        feedback.claim_type.value,
        feedback.applicable_law_country or feedback.court_country,
        is_b2b,
    )

    if ctx not in store:
        store[ctx] = LearningParams(context_key=ctx)
    params = store[ctx]

    # Determine evidence features present
    has_written_contract = any(e.type == EvidenceType.WRITTEN_CONTRACT for e in evidence_items)
    has_alternative = any(
        e.type in (EvidenceType.EMAIL_CHAIN, EvidenceType.MESSAGES, EvidenceType.BANK_RECORD)
        for e in evidence_items
    )

    won = feedback.outcome in (CaseOutcome.WON, CaseOutcome.SETTLED)
    conf = feedback.reason_confidence

    if feedback.reason_label:
        # Mode A: targeted update based on reason
        _update_with_reason(params, feedback.reason_label, has_written_contract,
                           has_alternative, won, conf)
    else:
        # Mode B: general update on all elements
        _update_general(params, has_written_contract, has_alternative, won, conf)

    params.n_observations += 1
    import time
    params.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Also update global fallback
    global_key = "*:*:*"
    if global_key not in store:
        store[global_key] = LearningParams(context_key=global_key)
    global_params = store[global_key]
    _update_general(global_params, has_written_contract, has_alternative, won, conf * 0.5)
    global_params.n_observations += 1


def _update_with_reason(
    params: LearningParams,
    reason: str,
    has_written_contract: bool,
    has_alternative: bool,
    won: bool,
    conf: float,
) -> None:
    """Targeted update: adjust the specific element that was the reason."""
    # Map reason_label to affected element
    reason_element_map = {
        "unschluessig_recht": "contract_basis",
        "contract_not_proven": "contract_basis",
        "performance_not_proven": "performance",
        "amount_not_proven": "amount_due",
        "defense_upheld_mangel": "no_defense",
        "defense_upheld_setoff": "no_defense",
    }

    element = reason_element_map.get(reason)
    if not element:
        # Unknown reason: do general update
        _update_general(params, has_written_contract, has_alternative, won, conf)
        return

    # Build condition key
    if has_written_contract:
        condition = "written_contract_present"
    elif has_alternative:
        condition = "alternative_present"
    else:
        condition = "no_evidence"

    cond_key = f"{element}:{condition}"

    alpha, beta = params.conditional_priors.get(cond_key, (_DEFAULT_ALPHA, _DEFAULT_BETA))
    if won:
        alpha += conf
    else:
        beta += conf
    params.conditional_priors[cond_key] = (round(alpha, 3), round(beta, 3))


def _update_general(
    params: LearningParams,
    has_written_contract: bool,
    has_alternative: bool,
    won: bool,
    conf: float,
) -> None:
    """General update: adjust all elements proportionally."""
    elements = ["contract_basis", "performance", "amount_due", "non_payment"]

    if has_written_contract:
        condition = "written_contract_present"
    elif has_alternative:
        condition = "alternative_present"
    else:
        condition = "no_evidence"

    for element in elements:
        cond_key = f"{element}:{condition}"
        alpha, beta = params.conditional_priors.get(cond_key, (_DEFAULT_ALPHA, _DEFAULT_BETA))
        update_weight = conf * 0.25  # Distribute across 4 elements
        if won:
            alpha += update_weight
        else:
            beta += update_weight
        params.conditional_priors[cond_key] = (round(alpha, 3), round(beta, 3))
