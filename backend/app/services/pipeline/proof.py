"""p_beweis computation — evidence strength assessment.

Element model per claim_type:
  For each required element, assess whether evidence supports it.
  Aggregate via sigmoid(Σ a_e * logit(p_e)).

Context-stratified Bayesian learning:
  Parameters namespaced by (claim_type, law_country, b2b/b2c).
  Hierarchical partial pooling when cell data is small.

IMPORTANT: Evidence items only — allegations handled in p_recht (no double-counting).
"""
from __future__ import annotations

from .math_utils import sigmoid, logit, clamp, beta_mean
from .models import (
    CaseInput,
    ClaimType,
    EvidenceItem,
    EvidenceType,
    LearningParams,
    ProofResult,
)


# Default base intercepts and weights per element
_DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "contract_basis": {
        "base": -0.5,
        "written_contract": 2.5,
        "email_chain": 1.5,
        "messages": 1.0,
        "bank_record": 0.5,
        "witness_statement": 0.8,
    },
    "performance": {
        "base": -0.3,
        "delivery_note": 2.0,
        "tracking": 1.8,
        "acceptance_protocol": 2.5,
        "invoice": 0.8,
        "email_chain": 1.0,
        "witness_statement": 0.8,
    },
    "amount_due": {
        "base": 0.0,
        "invoice": 2.0,
        "written_contract": 1.5,
        "bank_record": 1.0,
        "email_chain": 0.8,
    },
    "non_payment": {
        "base": 0.5,  # often plausible by default
        "bank_record": 1.5,
        "invoice": 0.5,
        "email_chain": 0.8,
    },
    "no_defense": {
        "base": 0.3,
        "written_contract": 0.5,
        "acceptance_protocol": 0.8,
    },
}

# Element lists per claim type
_CLAIM_ELEMENTS: dict[str, list[str]] = {
    "invoice": ["contract_basis", "performance", "amount_due", "non_payment"],
    "werklohn": ["contract_basis", "performance", "amount_due", "non_payment"],
    "refund": ["contract_basis", "amount_due"],
    "damages": ["contract_basis", "performance", "amount_due"],
    "unjust_enrichment": ["amount_due", "non_payment"],
    "other": ["contract_basis", "amount_due"],
}

# Evidence type -> feature name mapping
_EVIDENCE_FEATURE_MAP: dict[str, str] = {
    "written_contract": "written_contract",
    "email_chain": "email_chain",
    "invoice": "invoice",
    "delivery_note": "delivery_note",
    "tracking": "tracking",
    "acceptance_protocol": "acceptance_protocol",
    "messages": "messages",
    "witness_statement": "witness_statement",
    "bank_record": "bank_record",
    "expert_report": "expert_report",
}


def compute_p_beweis(
    case: CaseInput,
    evidence_items: list[EvidenceItem],
    learning_params: LearningParams | None = None,
) -> ProofResult:
    """Compute p_beweis from evidence items using element model.

    p_e = sigmoid(b_e + Σ w_ej * feature_j * strength_scale)
    p_beweis = sigmoid(Σ a_e * logit(p_e))

    Where a_e = element importance weight (uniform by default).
    """
    claim_type = case.claim_type.value
    elements = _CLAIM_ELEMENTS.get(claim_type, _CLAIM_ELEMENTS["other"])
    reasoning: list[str] = []
    missing_evidence: list[str] = []

    # Build feature vector from evidence items
    features: dict[str, float] = {}
    for ev in evidence_items:
        feature_name = _EVIDENCE_FEATURE_MAP.get(ev.type.value, "other")
        strength_scale = ev.strength_rating / 3.0  # normalize: 3 is neutral, 5 is strong
        if ev.authenticity_concern:
            strength_scale *= 0.5
        current = features.get(feature_name, 0.0)
        features[feature_name] = max(current, strength_scale)  # take strongest

    # Check for alternative evidence when no written contract
    has_written_contract = features.get("written_contract", 0) > 0
    has_alternative_basis = any(
        features.get(f, 0) > 0
        for f in ["email_chain", "messages", "bank_record", "witness_statement"]
    )

    # Compute per-element scores
    element_scores: dict[str, float] = {}
    logit_sum = 0.0

    for element_name in elements:
        weights = _get_element_weights(element_name, learning_params)
        base = weights.get("base", 0.0)
        score = base

        for feature_name, feature_val in features.items():
            w = weights.get(feature_name, 0.0)
            score += w * feature_val

        p_e = sigmoid(score)

        # Learning adjustment: shift based on historical outcomes
        if learning_params:
            p_e = _apply_learning_shift(p_e, element_name, features, learning_params)

        p_e = clamp(p_e, 0.01, 0.99)
        element_scores[element_name] = round(p_e, 4)
        logit_sum += logit(p_e)  # uniform weights (a_e = 1)

        if p_e < 0.3:
            missing_evidence.append(
                f"{element_name}: schwache Beweislage (p={p_e:.0%})"
            )
            reasoning.append(f"{element_name}: p_e={p_e:.2f} (schwach)")
        else:
            reasoning.append(f"{element_name}: p_e={p_e:.2f}")

    # Aggregate: p_beweis = sigmoid(mean of logits)
    if elements:
        mean_logit = logit_sum / len(elements)
        p_beweis = sigmoid(mean_logit)
    else:
        p_beweis = 0.5

    # Alternative evidence protection: don't let p_beweis collapse
    # when there's no written contract but strong alternative evidence
    if not has_written_contract and has_alternative_basis:
        p_beweis = max(p_beweis, 0.15)
        reasoning.append(
            "Kein schriftlicher Vertrag, aber alternative Beweismittel vorhanden "
            "→ p_beweis nicht unter 15%."
        )

    p_beweis = clamp(p_beweis, 0.01, 0.99)

    # Confidence based on evidence quantity
    confidence = min(0.9, 0.3 + 0.15 * len(evidence_items))

    return ProofResult(
        element_scores=element_scores,
        p_beweis=round(p_beweis, 4),
        confidence=round(confidence, 2),
        missing_evidence=missing_evidence,
        reasoning=reasoning,
    )


def _get_element_weights(
    element_name: str,
    learning_params: LearningParams | None,
) -> dict[str, float]:
    """Get weights for an element, possibly adjusted by learning."""
    base_weights = dict(_DEFAULT_WEIGHTS.get(element_name, {"base": 0.0}))

    if learning_params and learning_params.global_weights:
        for key, shift in learning_params.global_weights.items():
            if key.startswith(f"{element_name}:"):
                feature = key.split(":", 1)[1]
                base_weights[feature] = base_weights.get(feature, 0.0) + shift

    return base_weights


def _apply_learning_shift(
    p_e: float,
    element_name: str,
    features: dict[str, float],
    params: LearningParams,
) -> float:
    """Apply Bayesian learning shift to an element probability.

    Uses conditional Beta priors: θ_element|feature_present vs |feature_absent.
    Partial pooling with global when cell data is small.
    """
    # Check for conditional priors
    has_written = features.get("written_contract", 0) > 0
    has_alternative = any(
        features.get(f, 0) > 0
        for f in ["email_chain", "messages", "bank_record"]
    )

    if has_written:
        condition_key = f"{element_name}:written_contract_present"
    elif has_alternative:
        condition_key = f"{element_name}:alternative_present"
    else:
        condition_key = f"{element_name}:no_evidence"

    if condition_key in params.conditional_priors:
        alpha, beta = params.conditional_priors[condition_key]
        if alpha + beta > 2:  # meaningful data
            learned_p = beta_mean(alpha, beta)
            # Shrinkage: weight learned value by number of observations
            n = alpha + beta - 2  # subtract prior pseudocounts
            shrinkage = min(n / (n + 10), 0.8)  # max 80% weight on data
            p_e = (1 - shrinkage) * p_e + shrinkage * learned_p

    return p_e
