"""EV_betreiber calculation + take_case policy.

EV_betreiber = p_win*(fee_rate*claim) + p_win*(cost_compensation)
              - costs - (1-p_win)*(loss_costs_total)

Default take_case: p_obsiegen >= 0.80 AND EV_betreiber > 0 (configurable).
"""
from __future__ import annotations

from .models import CaseInput, CostModelParams, EVResult


def compute_ev(
    case: CaseInput,
    p_obsiegen: float,
    cost_params: CostModelParams | None = None,
) -> EVResult:
    """Compute expected value for the platform operator."""
    params = cost_params or CostModelParams()
    claim = case.claim_amount
    p_win = p_obsiegen

    # Revenue components
    expected_revenue = p_win * params.fee_rate * claim
    expected_cost_compensation = p_win * params.expected_cost_compensation_win

    # Cost components
    total_fixed = (
        params.costs_fixed + params.costs_filing + params.costs_service
        + params.costs_translation + params.costs_attorney
    )
    expected_enforcement = p_win * params.costs_enforcement
    expected_costs = total_fixed + expected_enforcement

    # Loss costs
    expected_loss_costs = (1 - p_win) * params.expected_loss_costs_total

    # Net EV
    ev_betreiber = (
        expected_revenue + expected_cost_compensation
        - expected_costs - expected_loss_costs
    )

    # Take case decision
    if params.take_case_requires_pwin_80:
        meets_threshold = p_win >= params.p_win_min
    else:
        meets_threshold = p_win >= params.p_win_min

    ev_positive = ev_betreiber > 0 if params.require_ev_positive else True
    take_case = meets_threshold and ev_positive

    # Reason
    if take_case:
        reason = (
            f"Annahme empfohlen: p_obsiegen={p_win:.0%} >= {params.p_win_min:.0%} "
            f"und EV={ev_betreiber:.2f} EUR > 0."
        )
    elif not meets_threshold:
        reason = (
            f"Ablehnung: p_obsiegen={p_win:.0%} < Schwelle {params.p_win_min:.0%}."
        )
    else:
        reason = (
            f"Ablehnung: EV={ev_betreiber:.2f} EUR <= 0 trotz "
            f"p_obsiegen={p_win:.0%}."
        )

    return EVResult(
        p_win=round(p_win, 4),
        expected_revenue=round(expected_revenue, 2),
        expected_cost_compensation=round(expected_cost_compensation, 2),
        expected_costs=round(expected_costs, 2),
        expected_loss_costs=round(expected_loss_costs, 2),
        ev_betreiber=round(ev_betreiber, 2),
        take_case=take_case,
        take_case_reason=reason,
        breakdown={
            "formula": (
                "EV = p_win * fee_rate * claim + p_win * cost_comp "
                "- costs - (1-p_win) * loss_total"
            ),
            "p_win": round(p_win, 4),
            "claim_amount": claim,
            "fee_rate": params.fee_rate,
            "expected_revenue": round(expected_revenue, 2),
            "expected_cost_compensation": round(expected_cost_compensation, 2),
            "total_fixed_costs": round(total_fixed, 2),
            "expected_enforcement_costs": round(expected_enforcement, 2),
            "expected_loss_costs": round(expected_loss_costs, 2),
            "ev_betreiber": round(ev_betreiber, 2),
            "threshold": params.p_win_min,
        },
    )
