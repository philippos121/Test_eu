"""Calibration and drift detection utilities.

- Brier score
- Reliability curve bins
- PSI-based drift detection
- Confidence adjustment
"""
from __future__ import annotations

import math
from typing import Optional


def brier_score(predictions: list[float], outcomes: list[bool]) -> float:
    """Compute Brier score: mean((p - y)^2). Lower = better calibrated."""
    if not predictions or len(predictions) != len(outcomes):
        return 1.0
    n = len(predictions)
    return sum((p - float(y)) ** 2 for p, y in zip(predictions, outcomes)) / n


def reliability_curve_bins(
    predictions: list[float],
    outcomes: list[bool],
    n_bins: int = 10,
) -> list[dict]:
    """Compute reliability curve bins.

    Returns list of {bin_center, mean_predicted, mean_observed, count}.
    """
    if not predictions:
        return []

    bins: list[dict] = []
    bin_width = 1.0 / n_bins

    for i in range(n_bins):
        lo = i * bin_width
        hi = (i + 1) * bin_width
        center = (lo + hi) / 2

        in_bin = [(p, o) for p, o in zip(predictions, outcomes) if lo <= p < hi]
        if not in_bin:
            continue

        mean_pred = sum(p for p, _ in in_bin) / len(in_bin)
        mean_obs = sum(float(o) for _, o in in_bin) / len(in_bin)

        bins.append({
            "bin_center": round(center, 2),
            "mean_predicted": round(mean_pred, 4),
            "mean_observed": round(mean_obs, 4),
            "count": len(in_bin),
        })

    return bins


def psi(
    expected: list[float],
    actual: list[float],
    n_bins: int = 10,
) -> float:
    """Population Stability Index for drift detection.

    PSI < 0.1: no significant drift
    PSI 0.1-0.25: moderate drift
    PSI > 0.25: significant drift
    """
    if not expected or not actual:
        return 0.0

    bin_width = 1.0 / n_bins
    total_psi = 0.0

    for i in range(n_bins):
        lo = i * bin_width
        hi = (i + 1) * bin_width

        exp_pct = sum(1 for x in expected if lo <= x < hi) / max(len(expected), 1)
        act_pct = sum(1 for x in actual if lo <= x < hi) / max(len(actual), 1)

        exp_pct = max(exp_pct, 0.0001)
        act_pct = max(act_pct, 0.0001)

        total_psi += (act_pct - exp_pct) * math.log(act_pct / exp_pct)

    return round(total_psi, 4)


def check_drift(
    recent_predictions: list[float],
    historical_predictions: list[float],
    threshold: float = 0.25,
) -> tuple[bool, float, str]:
    """Check for distribution drift.

    Returns (is_drift, psi_value, message).
    """
    psi_val = psi(historical_predictions, recent_predictions)

    if psi_val > threshold:
        return True, psi_val, (
            f"Signifikanter Drift erkannt (PSI={psi_val:.3f} > {threshold}). "
            "Konfidenz wird gesenkt."
        )
    elif psi_val > threshold / 2:
        return False, psi_val, (
            f"Moderater Drift (PSI={psi_val:.3f}). Beobachtung empfohlen."
        )
    else:
        return False, psi_val, f"Kein signifikanter Drift (PSI={psi_val:.3f})."
