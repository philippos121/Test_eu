"""Mathematical utilities for the scoring pipeline."""
from __future__ import annotations

import math


def sigmoid(x: float) -> float:
    """Standard logistic sigmoid σ(x) = 1/(1+e^-x), clamped to avoid overflow."""
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    """Inverse sigmoid: logit(p) = log(p/(1-p))."""
    p = clamp(p, 1e-9, 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def beta_mean(alpha: float, beta: float) -> float:
    if alpha + beta <= 0:
        return 0.5
    return alpha / (alpha + beta)


def beta_ci(alpha: float, beta: float, level: float = 0.90) -> tuple[float, float]:
    """Approximate CI for Beta distribution using normal approximation."""
    import statistics as _st
    mean = beta_mean(alpha, beta)
    n = alpha + beta
    if n <= 2:
        return (0.0, 1.0)
    var = (alpha * beta) / (n * n * (n + 1))
    sd = math.sqrt(var)
    z = 1.645 if level == 0.90 else 1.96
    lo = clamp(mean - z * sd)
    hi = clamp(mean + z * sd)
    return (round(lo, 4), round(hi, 4))


def weighted_average(values: list[tuple[float, float]]) -> float:
    """Weighted average of (value, weight) pairs."""
    total_weight = sum(w for _, w in values)
    if total_weight <= 0:
        return 0.5
    return sum(v * w for v, w in values) / total_weight
