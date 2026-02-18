"""p_eintreibung computation — recovery probability.

MUST NOT be computed without prior:
  a) Insolvency register check
  b) Web signals check
If checks not done: p_eintreibung = None, pending_external_checks = True.
"""
from __future__ import annotations

from .math_utils import sigmoid, logit, clamp
from .models import (
    InsolvencyStatus,
    RecoveryInput,
    RecoveryResult,
    RecoverySignal,
)
from .recovery_checks import InsolvencyCheckProvider, WebSignalsProvider
from .search import SearchClient
from .fetch import FetchClient


async def compute_p_eintreibung(
    recovery_input: RecoveryInput,
    debtor_country: str,
    do_external_checks: bool = True,
    search_client: SearchClient | None = None,
    fetch_client: FetchClient | None = None,
) -> RecoveryResult:
    """Compute p_eintreibung with external checks.

    If do_external_checks is False: returns None/pending.
    """
    if not do_external_checks:
        return RecoveryResult(
            insolvency_status=InsolvencyStatus.CHECK_PENDING,
            p_eintreibung=None,
            pending_external_checks=True,
            ampel="pending",
            reasoning=["Externe Checks nicht durchgeführt — p_eintreibung ausstehend."],
        )

    search = search_client or SearchClient()
    fetch = fetch_client or FetchClient()

    # 1. Insolvency check
    insolvency_provider = InsolvencyCheckProvider(search, fetch)
    insolvency_status, insolvency_signals = await insolvency_provider.check(
        recovery_input, debtor_country
    )

    # 2. Web signals
    web_provider = WebSignalsProvider(search, fetch)
    web_signals = await web_provider.check(recovery_input, debtor_country)

    all_signals = insolvency_signals + web_signals
    reasoning: list[str] = []

    # 3. Compute p_eintreibung
    if insolvency_status == InsolvencyStatus.INSOLVENT:
        p_eintreibung = 0.05
        uncertainty = (0.01, 0.15)
        ampel = "red"
        reasoning.append("Insolvenz-Signale gefunden → p_eintreibung sehr niedrig (5%).")
    elif insolvency_status == InsolvencyStatus.UNKNOWN:
        # Base estimate from other signals
        p_eintreibung = _estimate_from_signals(recovery_input, web_signals, reasoning)
        p_eintreibung *= 0.7  # Reduce due to unknown insolvency status
        uncertainty = (max(0.01, p_eintreibung - 0.2), min(0.99, p_eintreibung + 0.2))
        ampel = "yellow"
        reasoning.append("Insolvenzstatus unklar → Konfidenz eingeschränkt.")
    else:  # SOLVENT
        p_eintreibung = _estimate_from_signals(recovery_input, web_signals, reasoning)
        uncertainty = (max(0.01, p_eintreibung - 0.15), min(0.99, p_eintreibung + 0.15))
        ampel = "green" if p_eintreibung >= 0.6 else "yellow"

    p_eintreibung = clamp(p_eintreibung, 0.01, 0.99)

    return RecoveryResult(
        insolvency_status=insolvency_status,
        signals=all_signals,
        p_eintreibung=round(p_eintreibung, 4),
        uncertainty_band=(round(uncertainty[0], 4), round(uncertainty[1], 4)),
        ampel=ampel,
        pending_external_checks=False,
        reasoning=reasoning,
    )


def _estimate_from_signals(
    recovery: RecoveryInput,
    web_signals: list[RecoverySignal],
    reasoning: list[str],
) -> float:
    """Estimate recovery probability from non-insolvency signals."""
    score = 0.0  # logit-space accumulator

    # Payment history
    if recovery.payment_history == "good":
        score += 1.0
        reasoning.append("Zahlungshistorie: gut → +1.0")
    elif recovery.payment_history == "bad":
        score -= 1.5
        reasoning.append("Zahlungshistorie: schlecht → -1.5")

    # Known bank account
    if recovery.known_bank_account:
        score += 0.8
        reasoning.append("Bankkonto bekannt → +0.8")
    else:
        score -= 0.3

    # Known employer/income
    if recovery.known_employer_or_income_source:
        score += 0.5
        reasoning.append("Einkommensquelle bekannt → +0.5")

    # Address quality
    if recovery.address_quality == "high":
        score += 0.3
    elif recovery.address_quality == "low":
        score -= 0.5
        reasoning.append("Adressqualität niedrig → -0.5")

    # Company vs private
    if recovery.debtor_type.value == "company":
        score += 0.2  # Companies slightly easier to enforce against

    # Enforcement complexity
    if recovery.enforcement_complexity.value == "cross_border_eu":
        score -= 0.5
        reasoning.append("Grenzüberschreitende Vollstreckung (EU) → -0.5")
    elif recovery.enforcement_complexity.value == "cross_border_non_eu":
        score -= 1.5
        reasoning.append("Grenzüberschreitende Vollstreckung (Nicht-EU) → -1.5")

    # Prior dunning response
    if recovery.prior_dunning:
        score += 0.3

    # Debtor disputes
    if recovery.debtor_disputes:
        score -= 0.5

    # Web signal penalties
    negative_count = sum(
        1 for s in web_signals
        if "negativ" in s.value.lower() or "complaint" in s.value.lower()
    )
    if negative_count > 0:
        score -= 0.3 * negative_count
        reasoning.append(f"{negative_count} negative Web-Signale → -{0.3 * negative_count:.1f}")

    return sigmoid(score)
