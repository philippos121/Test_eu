"""Pure-NumPy Mini Neural Network for ESCP case outcome prediction.

Architecture : Input(40) → Dense(32, ReLU) → Dense(16, ReLU) → Dense(3, Softmax)
Loss         : Categorical cross-entropy (3 classes)
Optimizer    : Adam (β₁=0.9, β₂=0.999, ε=1e-8)

Output classes:
  0 — full_success   : Judgment won, payment received in full
  1 — partial_success: Settled (with or without full payment)
  2 — failure        : Judgment lost, collection failed, or service failed

Blend into scoring pipeline:
  p_cash_nn = P[0] + 0.5 × P[1]     (expected weighted recovery)
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Case, CaseEvent, CaseEventType, CaseStatus, NNModel

# ---------------------------------------------------------------------------
# Feature definitions  (40 features)
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    # Block A — Claim (6)
    "log_claim_amount",        # log10(amount/1000), clipped [-2, 2]
    "claim_type_zahlung",      # Zahlungsklage
    "claim_type_herausgabe",   # Herausgabeklage
    "claim_type_schadenersatz",# Schadensersatzklage
    "rechtsgrund_vertrag",     # vertraglicher Anspruch
    "rechtsgrund_delikt",      # außervertraglicher Schadensersatz
    # Block B — Parties (5)
    "claimant_is_legal",       # Kläger juristische Person
    "defendant_is_legal",      # Beklagter juristische Person
    "is_b2b",                  # beide juristische Personen
    "is_b2c",                  # Kläger juristisch, Beklagter natürlich
    "is_cross_border",         # grenzüberschreitend
    # Block C — Kläger-Land (4)
    "claimant_dach",           # DE, AT
    "claimant_fr_be_lu",       # FR, BE, LU
    "claimant_it_es_pt",       # IT, ES, PT
    "claimant_eastern_eu",     # PL, CZ, SK, HU, RO, BG, EE, LT, LV, HR
    # Block D — Beklagter-Land (5)
    "defendant_de_at",         # DE, AT
    "defendant_fr_be",         # FR, BE, LU
    "defendant_it_es_pt",      # IT, ES, PT
    "defendant_eastern_eu",    # PL, CZ, SK, HU, RO, BG, EE, LT, LV, HR
    "defendant_other_eu",      # NL, SE, DK, FI, IE, GR, CY, MT, SI
    # Block E — Zeit (3)
    "year_norm",               # (Jahr - 2020) / 10, geclippt [0, 1]
    "quarter_h1",              # Q1 oder Q2
    "quarter_q4",              # Q4
    # Block F — Beweise (5)
    "has_contract",            # schriftlicher Vertrag vorhanden
    "has_delivery_proof",      # Liefer-/Leistungsnachweis
    "has_invoice",             # Rechnung vorhanden
    "has_dunning",             # Mahnung/Fristsetzung
    "has_jurisdiction_agr",    # Gerichtsstandsvereinbarung
    # Block G — Schuldnersituation (2)
    "has_insolvency",          # Insolvenzrisiko
    "has_quality_dispute",     # Qualitätsstreit / Mängel
    # Block H — Einwendungen (9)
    "defense_no_contract",     # kein Vertrag (bestreitet Vertragsschluss)
    "defense_not_fulfilled",   # Vertrag nicht erfüllt
    "defense_defective",       # mangelhafte Erfüllung
    "defense_irrtum",          # Irrtum / mistake
    "defense_no_damage",       # kein Schaden
    "defense_no_causation",    # keine Kausalität
    "defense_no_fault",        # kein Verschulden
    "defense_verjährung",      # Verjährung / limitation
    "defense_set_off",         # Aufrechnung / set-off
    # Block I — Sonstiges (1)
    "is_services",             # Dienstleistungsvertrag (nicht Warenlieferung)
]

INPUT_DIM    = len(FEATURE_NAMES)   # 40
HIDDEN_DIMS  = [32, 16]
OUTPUT_DIM   = 3                    # full_success, partial_success, failure
ARCHITECTURE = {"input": INPUT_DIM, "hidden": HIDDEN_DIMS, "output": OUTPUT_DIM}

# Outcome class labels
OUTCOME_FULL    = 0   # Vollerfolg: Urteil + volle Zahlung
OUTCOME_PARTIAL = 1   # Teilerfolg: Vergleich / Teilzahlung
OUTCOME_FAILURE = 2   # Misserfolg: Abweisung / Vollstreckungsversagen

_EU_EASTERN = {"PL", "CZ", "SK", "HU", "RO", "BG", "EE", "LT", "LV", "HR"}
_EU_DACH    = {"DE", "AT"}
_EU_FR_BE   = {"FR", "BE", "LU"}
_EU_IT_ES   = {"IT", "ES", "PT"}
_EU_OTHER   = {"NL", "SE", "DK", "FI", "IE", "GR", "CY", "MT", "SI", "CH"}


def extract_features(case: Case) -> np.ndarray:
    """Extract a normalised 40-dim feature vector from a Case ORM object."""
    amount = case.claim_amount or 0.0
    log_amount = float(np.clip(math.log10(max(amount, 1.0) / 1000.0), -2.0, 2.0))

    text = " ".join(filter(None, [
        (case.claim_evidence    or ""),
        (case.claim_basis       or ""),
        (case.claim_description or ""),
        (getattr(case, "assessment_summary", None) or ""),
    ])).lower()

    # --- Block A: Claim type & legal basis ---
    claim_zahlung = 1.0 if any(w in text for w in [
        "zahlung", "kaufpreis", "rechnung", "unbezahlt", "invoice", "fällig",
        "faktur", "zahlungsverzug", "zahlungsaufforderung",
    ]) else 0.0
    claim_herausgabe = 1.0 if any(w in text for w in [
        "herausgabe", "rückgabe", "rückübereignung", "return", "surrender",
    ]) else 0.0
    claim_schadenersatz = 1.0 if any(w in text for w in [
        "schadensersatz", "schadenersatz", "damages", "schaden", "ersatz",
        "entschädigung", "kompensation",
    ]) else 0.0
    rg_vertrag = 1.0 if any(w in text for w in [
        "vertrag", "kaufvertrag", "werkvertrag", "dienstvertrag",
        "contract", "auftrag", "bestellung", "liefervertrag",
    ]) else 0.0
    rg_delikt = 1.0 if any(w in text for w in [
        "delikt", "unerlaubte handlung", "tort", "negligence",
        "haftung", "verschulden außervertraglich",
    ]) else 0.0

    # --- Block B: Parties ---
    c_legal = 1.0 if case.claimant_is_legal_person else 0.0
    d_legal = 1.0 if case.defendant_is_legal_person else 0.0
    is_b2b  = 1.0 if (case.claimant_is_legal_person and case.defendant_is_legal_person) else 0.0
    is_b2c  = 1.0 if (case.claimant_is_legal_person and not case.defendant_is_legal_person) else 0.0
    is_xb   = 1.0 if case.is_cross_border else 0.0

    # --- Block C: Kläger-Land ---
    claimant_cc = (
        getattr(case, "claimant_domicile_country", None)
        or getattr(case, "claimant_country", None)
        or getattr(case, "court_country", None)
        or ""
    ).upper().strip()
    c_dach     = 1.0 if claimant_cc in _EU_DACH    else 0.0
    c_fr_be    = 1.0 if claimant_cc in _EU_FR_BE   else 0.0
    c_it_es    = 1.0 if claimant_cc in _EU_IT_ES   else 0.0
    c_eastern  = 1.0 if claimant_cc in _EU_EASTERN else 0.0

    # --- Block D: Beklagter-Land ---
    def_cc = (
        getattr(case, "defendant_domicile_country", None)
        or getattr(case, "defendant_country", None)
        or ""
    ).upper().strip()
    d_de_at    = 1.0 if def_cc in _EU_DACH    else 0.0
    d_fr_be    = 1.0 if def_cc in _EU_FR_BE   else 0.0
    d_it_es    = 1.0 if def_cc in _EU_IT_ES   else 0.0
    d_eastern  = 1.0 if def_cc in _EU_EASTERN else 0.0
    d_other_eu = 1.0 if def_cc in _EU_OTHER   else 0.0

    # --- Block E: Zeit ---
    try:
        created = case.created_at
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        year_norm = float(np.clip((created.year - 2020) / 10.0, 0.0, 1.0))
        month = created.month
    except Exception:
        year_norm = 0.5
        month = 6
    quarter_h1 = 1.0 if month <= 6 else 0.0
    quarter_q4 = 1.0 if month >= 10 else 0.0

    # --- Block F: Beweise ---
    has_contract = 1.0 if any(w in text for w in [
        "vertrag", "contract", "auftrag", "kaufvertrag", "werkvertrag",
        "bestellung", "auftragsbestätigung", "schriftlich vereinbart",
    ]) else 0.0
    has_delivery = 1.0 if any(w in text for w in [
        "lieferschein", "delivery", "liefernachweis", "lieferung",
        "empfangsbestätigung", "abnahme", "leistungsnachweis",
    ]) else 0.0
    has_invoice = 1.0 if any(w in text for w in [
        "rechnung", "invoice", "fällig", "faktur", "zahlungsziel",
    ]) else 0.0
    has_dunning = 1.0 if any(w in text for w in [
        "mahnung", "dunning", "reminder", "zahlungserinnerung",
        "fristsetzung", "mahnschreiben",
    ]) else 0.0
    has_juris_agr = 1.0 if any(w in text for w in [
        "gerichtsstandsvereinbarung", "jurisdiction agreement",
        "gerichtsstand vereinbart", "vereinbarter gerichtsstand",
    ]) else 0.0

    # --- Block G: Schuldnersituation ---
    has_insolvency = 1.0 if any(w in text for w in [
        "insolv", "bankrupt", "insolvenz", "konkurs", "pleite", "überschuldung",
    ]) else 0.0
    has_quality = 1.0 if any(w in text for w in [
        "qualit", "mängel", "mangel", "defect", "beschwerde",
        "reklamation", "mangelhafte", "mängelhaftung",
    ]) else 0.0

    # --- Block H: Einwendungen ---
    def_no_contract = 1.0 if any(w in text for w in [
        "kein vertrag", "bestreitet vertragsschluss", "no contract",
        "vertrag nicht geschlossen", "kein vertragsschluss",
    ]) else 0.0
    def_not_fulfilled = 1.0 if any(w in text for w in [
        "nicht erfüllt", "nicht erbracht", "leistung nicht erbracht",
        "not performed", "non-performance",
    ]) else 0.0
    def_defective = 1.0 if any(w in text for w in [
        "mangelhaft", "mängel", "defective", "qualitätsmangel",
        "mangelhafte erfüllung", "schlechte leistung",
    ]) else 0.0
    def_irrtum = 1.0 if any(w in text for w in [
        "irrtum", "mistake", "anfechtung wegen irrtum", "willensmangel",
    ]) else 0.0
    def_no_damage = 1.0 if any(w in text for w in [
        "kein schaden", "no damage", "schaden nicht eingetreten",
        "schaden bestritten",
    ]) else 0.0
    def_no_causation = 1.0 if any(w in text for w in [
        "keine kausalität", "kein kausalzusammenhang", "no causation",
        "kausalität fehlt",
    ]) else 0.0
    def_no_fault = 1.0 if any(w in text for w in [
        "kein verschulden", "kein vorsatz", "keine fahrlässigkeit",
        "no fault", "no negligence", "sorgfalt eingehalten",
    ]) else 0.0
    def_verjährung = 1.0 if any(w in text for w in [
        "verjährung", "limitation period", "verjährt", "frist abgelaufen",
        "prescription",
    ]) else 0.0
    def_set_off = 1.0 if any(w in text for w in [
        "aufrechnung", "set-off", "gegenforderung", "verrechnung",
        "counterclaim",
    ]) else 0.0

    # --- Block I: Sonstiges ---
    is_services = 1.0 if any(w in text for w in [
        "dienstleist", "service", "wartung", "beratung", "support",
        "reparatur", "werkvertrag", "consulting",
    ]) else 0.0

    return np.array([
        log_amount,
        claim_zahlung, claim_herausgabe, claim_schadenersatz,
        rg_vertrag, rg_delikt,
        c_legal, d_legal, is_b2b, is_b2c, is_xb,
        c_dach, c_fr_be, c_it_es, c_eastern,
        d_de_at, d_fr_be, d_it_es, d_eastern, d_other_eu,
        year_norm, quarter_h1, quarter_q4,
        has_contract, has_delivery, has_invoice, has_dunning, has_juris_agr,
        has_insolvency, has_quality,
        def_no_contract, def_not_fulfilled, def_defective, def_irrtum,
        def_no_damage, def_no_causation, def_no_fault, def_verjährung,
        def_set_off,
        is_services,
    ], dtype=np.float64)


def get_outcome(events: list[CaseEvent]) -> Optional[int]:
    """Return outcome class (0/1/2) or None (unknown / insufficient events).

    Class 0 — full_success   : PAYMENT_RECEIVED (after JUDGMENT_WIN or DEFAULT)
    Class 1 — partial_success: SETTLED (negotiated resolution)
    Class 2 — failure        : JUDGMENT_LOSS or COLLECTION_FAILED
    None    — still open / service failed / no terminal event yet
    """
    types = {e.event_type for e in events}
    if CaseEventType.JUDGMENT_LOSS in types:
        return OUTCOME_FAILURE
    if CaseEventType.COLLECTION_FAILED in types:
        return OUTCOME_FAILURE
    if CaseEventType.SETTLED in types:
        return OUTCOME_PARTIAL   # settled = partial (may include payment)
    if CaseEventType.PAYMENT_RECEIVED in types:
        return OUTCOME_FULL      # full payment received after judgment
    return None


def _to_one_hot(labels: np.ndarray, n_classes: int = OUTPUT_DIM) -> np.ndarray:
    """Convert integer class labels (n,) to one-hot matrix (n, n_classes)."""
    n = len(labels)
    oh = np.zeros((n, n_classes), dtype=np.float64)
    oh[np.arange(n), labels.astype(int)] = 1.0
    return oh


# ---------------------------------------------------------------------------
# Neural network (3-class softmax + categorical cross-entropy)
# ---------------------------------------------------------------------------

class NeuralNet:
    """2-hidden-layer MLP with Adam optimizer.

    Architecture: Input(40) → Dense(32, ReLU) → Dense(16, ReLU) → Dense(3, Softmax)
    Loss        : Categorical cross-entropy
    Backprop    : dZ_output = y_hat - y_true  (same elegant form as BCE+sigmoid)
    """

    def __init__(self, hidden_dims: list[int] = HIDDEN_DIMS, seed: int = 42):
        rng = np.random.RandomState(seed)
        dims = [INPUT_DIM] + hidden_dims + [OUTPUT_DIM]
        self.W: list[np.ndarray] = []
        self.b: list[np.ndarray] = []
        for i in range(len(dims) - 1):
            limit = math.sqrt(6.0 / (dims[i] + dims[i + 1]))
            self.W.append(rng.uniform(-limit, limit, (dims[i], dims[i + 1])))
            self.b.append(np.zeros((1, dims[i + 1])))
        self._reset_adam()

    def _reset_adam(self) -> None:
        self.mW = [np.zeros_like(w) for w in self.W]
        self.vW = [np.zeros_like(w) for w in self.W]
        self.mb = [np.zeros_like(b) for b in self.b]
        self.vb = [np.zeros_like(b) for b in self.b]
        self.t: int = 0

    @staticmethod
    def _relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, x)

    @staticmethod
    def _relu_d(x: np.ndarray) -> np.ndarray:
        return (x > 0.0).astype(np.float64)

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax."""
        x_shift = x - np.max(x, axis=1, keepdims=True)
        ex = np.exp(x_shift)
        return ex / (np.sum(ex, axis=1, keepdims=True) + 1e-12)

    def forward(self, X: np.ndarray) -> tuple[np.ndarray, list, list]:
        """Return (y_hat, Z_list, A_list) for backprop."""
        Z_list: list[np.ndarray] = []
        A_list: list[np.ndarray] = [X]
        A = X
        for i in range(len(self.W) - 1):
            Z = A @ self.W[i] + self.b[i]
            A = self._relu(Z)
            Z_list.append(Z)
            A_list.append(A)
        Z_out = A @ self.W[-1] + self.b[-1]
        y_hat = self._softmax(Z_out)
        Z_list.append(Z_out)
        A_list.append(y_hat)
        return y_hat, Z_list, A_list

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Returns class probabilities (n, 3)."""
        y_hat, _, _ = self.forward(X)
        return y_hat

    def train_epoch(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        lr: float = 0.005,
        l2: float = 1e-4,
        batch_size: int = 16,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
    ) -> float:
        """One full pass. y is one-hot (n, 3). Returns mean CCE loss."""
        n = X.shape[0]
        idx = np.random.permutation(n)
        X_s, y_s = X[idx], y[idx]
        total_loss = 0.0
        n_batches = 0

        for start in range(0, n, batch_size):
            Xb = X_s[start:start + batch_size]
            yb = y_s[start:start + batch_size]
            m  = Xb.shape[0]

            y_hat, Z_list, A_list = self.forward(Xb)

            # CCE loss (for monitoring)
            loss = -np.mean(np.sum(yb * np.log(y_hat + 1e-12), axis=1))
            total_loss += loss
            n_batches  += 1

            # Combined gradient: dCCE/dZ_softmax = (y_hat - y_true) / m
            dZ = (y_hat - yb) / m

            self.t += 1

            for i in reversed(range(len(self.W))):
                A_prev = A_list[i]
                dW = A_prev.T @ dZ + l2 * self.W[i]
                db = np.sum(dZ, axis=0, keepdims=True)

                self.mW[i] = beta1 * self.mW[i] + (1 - beta1) * dW
                self.vW[i] = beta2 * self.vW[i] + (1 - beta2) * dW ** 2
                self.mb[i] = beta1 * self.mb[i] + (1 - beta1) * db
                self.vb[i] = beta2 * self.vb[i] + (1 - beta2) * db ** 2

                mW_hat = self.mW[i] / (1 - beta1 ** self.t)
                vW_hat = self.vW[i] / (1 - beta2 ** self.t)
                mb_hat = self.mb[i] / (1 - beta1 ** self.t)
                vb_hat = self.vb[i] / (1 - beta2 ** self.t)

                self.W[i] -= lr * mW_hat / (np.sqrt(vW_hat) + eps)
                self.b[i] -= lr * mb_hat / (np.sqrt(vb_hat) + eps)

                if i > 0:
                    dA_prev = dZ @ self.W[i].T
                    dZ = dA_prev * self._relu_d(Z_list[i - 1])

        return total_loss / max(n_batches, 1)

    def to_dict(self) -> dict:
        return {
            "hidden_dims": HIDDEN_DIMS,
            "output_dim":  OUTPUT_DIM,
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NeuralNet":
        net = cls.__new__(cls)
        net.W = [np.array(w) for w in d["W"]]
        net.b = [np.array(b) for b in d["b"]]
        net._reset_adam()
        return net


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

async def collect_training_data(
    db: AsyncSession,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Load all completed cases with known outcomes.

    Returns (X, y_onehot, case_ids, case_titles).
    X: (n, 40),  y_onehot: (n, 3) one-hot encoded class labels.
    """
    cases_result = await db.execute(
        select(Case).where(Case.status == CaseStatus.COMPLETED)
    )
    cases = cases_result.scalars().all()

    X_list:     list[np.ndarray] = []
    label_list: list[int]        = []
    ids:        list[str]        = []
    titles:     list[str]        = []

    for case in cases:
        ev_result = await db.execute(
            select(CaseEvent).where(CaseEvent.case_id == case.id)
        )
        events  = ev_result.scalars().all()
        outcome = get_outcome(events)
        if outcome is None:
            continue
        X_list.append(extract_features(case))
        label_list.append(outcome)
        ids.append(str(case.id))
        titles.append(case.title)

    if not X_list:
        return (
            np.zeros((0, INPUT_DIM)),
            np.zeros((0, OUTPUT_DIM)),
            [],
            [],
        )
    X      = np.array(X_list)
    labels = np.array(label_list, dtype=int)
    y_oh   = _to_one_hot(labels)
    return X, y_oh, ids, titles


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

async def train_model(
    db: AsyncSession,
    *,
    epochs: int = 300,
    lr: float = 0.005,
    l2: float = 1e-4,
    batch_size: int = 16,
    val_split: float = 0.2,
    seed: int = 42,
) -> dict:
    """Train a new NeuralNet on all available completed cases. Returns summary."""
    X, y, case_ids, _ = await collect_training_data(db)
    n = len(case_ids)

    if n < 3:
        return {
            "success": False,
            "message": f"Zu wenige Trainingsfälle ({n}). Mindestens 3 benötigt.",
            "n_train_cases": n,
        }

    rng = np.random.RandomState(seed)
    idx = rng.permutation(n)
    val_size  = max(1, int(n * val_split))
    val_idx   = idx[:val_size]
    train_idx = idx[val_size:]

    X_train, y_train = X[train_idx], y[train_idx]
    X_val,   y_val   = X[val_idx],   y[val_idx]

    net = NeuralNet(hidden_dims=HIDDEN_DIMS, seed=seed)

    history: list[dict] = []
    for epoch in range(epochs):
        train_loss = net.train_epoch(
            X_train, y_train,
            lr=lr, l2=l2, batch_size=batch_size,
        )
        if epoch % 20 == 0 or epoch == epochs - 1:
            val_pred   = net.predict(X_val)
            val_loss   = float(-np.mean(np.sum(y_val  * np.log(val_pred  + 1e-12), axis=1)))
            tr_pred    = net.predict(X_train)
            tr_loss_m  = float(-np.mean(np.sum(y_train * np.log(tr_pred  + 1e-12), axis=1)))
            # Accuracy: argmax match
            val_acc    = float(np.mean(np.argmax(val_pred, axis=1) == np.argmax(y_val,   axis=1)))
            tr_acc     = float(np.mean(np.argmax(tr_pred,  axis=1) == np.argmax(y_train, axis=1)))
            history.append({
                "epoch":      epoch + 1,
                "train_loss": round(float(train_loss), 4),
                "val_loss":   round(val_loss, 4),
                "train_acc":  round(tr_acc, 4),
                "val_acc":    round(val_acc, 4),
            })

    # Final metrics
    train_pred = net.predict(X_train)
    val_pred   = net.predict(X_val)
    train_acc  = float(np.mean(np.argmax(train_pred, axis=1) == np.argmax(y_train, axis=1)))
    val_acc    = float(np.mean(np.argmax(val_pred,   axis=1) == np.argmax(y_val,   axis=1)))

    # Feature importance: mean |first-layer weight| per input feature
    importance_raw = np.mean(np.abs(net.W[0]), axis=1).tolist()
    imp_ranked = sorted(
        [{"name": FEATURE_NAMES[i], "importance": round(importance_raw[i], 5)}
         for i in range(INPUT_DIM)],
        key=lambda x: x["importance"],
        reverse=True,
    )

    # Deactivate old models
    old_models = (await db.execute(
        select(NNModel).where(NNModel.is_active == True)
    )).scalars().all()
    for m in old_models:
        m.is_active = False

    all_models = (await db.execute(select(NNModel))).scalars().all()
    version    = max((m.version for m in all_models), default=0) + 1

    nn_row = NNModel(
        version=version,
        is_active=True,
        feature_names=FEATURE_NAMES,
        architecture=ARCHITECTURE,
        weights=net.to_dict(),
        training_history=history,
        feature_importance=imp_ranked,
        hyperparams={"epochs": epochs, "lr": lr, "l2": l2, "batch_size": batch_size},
        n_train_cases=int(len(train_idx)),
        n_val_cases=int(len(val_idx)),
        train_accuracy=round(train_acc, 4),
        val_accuracy=round(val_acc, 4),
    )
    db.add(nn_row)
    await db.commit()
    await db.refresh(nn_row)

    return {
        "success":        True,
        "message":        f"Modell v{version} auf {len(train_idx)} Fällen trainiert (3-Klassen CCE).",
        "version":        version,
        "n_train_cases":  int(len(train_idx)),
        "n_val_cases":    int(len(val_idx)),
        "train_accuracy": round(train_acc, 4),
        "val_accuracy":   round(val_acc, 4),
        "history":        history,
        "feature_importance": imp_ranked,
    }


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

async def predict_for_case(
    case: Case, db: AsyncSession
) -> tuple[Optional[float], Optional[dict]]:
    """Run NN forward pass for a case.

    Returns (p_cash_nn, meta_dict) or (None, None) if no active model.

    p_cash_nn = P[full_success] + 0.5 × P[partial_success]
    This is a weighted expected-recovery probability used for blending.
    """
    result = await db.execute(
        select(NNModel)
        .where(NNModel.is_active == True)
        .order_by(NNModel.version.desc())
        .limit(1)
    )
    nn_row = result.scalar_one_or_none()
    if nn_row is None:
        return None, None

    net  = NeuralNet.from_dict(nn_row.weights)
    X    = extract_features(case).reshape(1, -1)
    probs = net.predict(X)[0]          # shape (3,)

    p_full    = float(probs[OUTCOME_FULL])
    p_partial = float(probs[OUTCOME_PARTIAL])
    p_failure = float(probs[OUTCOME_FAILURE])
    p_cash_nn = float(np.clip(p_full + 0.5 * p_partial, 0.0, 1.0))

    w = nn_blend_weight(nn_row.n_train_cases)
    meta = {
        "p_nn_raw":         round(p_cash_nn, 4),
        "p_full_success":   round(p_full,    4),
        "p_partial_success":round(p_partial, 4),
        "p_failure":        round(p_failure, 4),
        "nn_weight":        round(w, 4),
        "n_train_cases":    nn_row.n_train_cases,
        "model_version":    nn_row.version,
        "val_accuracy":     nn_row.val_accuracy,
    }
    return p_cash_nn, meta


async def get_all_predictions(db: AsyncSession) -> list[dict]:
    """Return NN predictions for all completed cases (dashboard display)."""
    result = await db.execute(
        select(NNModel)
        .where(NNModel.is_active == True)
        .order_by(NNModel.version.desc())
        .limit(1)
    )
    nn_row = result.scalar_one_or_none()
    if nn_row is None:
        return []

    net = NeuralNet.from_dict(nn_row.weights)
    X, y_oh, ids, titles = await collect_training_data(db)
    if len(ids) == 0:
        return []

    probs  = net.predict(X)           # (n, 3)
    labels = np.argmax(y_oh, axis=1)  # true class indices
    preds  = np.argmax(probs, axis=1) # predicted class indices

    class_labels = ["Vollerfolg", "Teilerfolg", "Misserfolg"]
    out = []
    for i, (case_id, title) in enumerate(zip(ids, titles)):
        p_full    = float(probs[i, OUTCOME_FULL])
        p_partial = float(probs[i, OUTCOME_PARTIAL])
        p_cash_nn = float(np.clip(p_full + 0.5 * p_partial, 0.0, 1.0))
        out.append({
            "case_id":          case_id,
            "case_title":       title,
            "p_nn":             round(p_cash_nn, 4),
            "p_full":           round(p_full, 4),
            "p_partial":        round(float(probs[i, OUTCOME_PARTIAL]), 4),
            "p_failure":        round(float(probs[i, OUTCOME_FAILURE]), 4),
            "actual_class":     int(labels[i]),
            "actual_label":     class_labels[int(labels[i])],
            "predicted_class":  int(preds[i]),
            "predicted_label":  class_labels[int(preds[i])],
            "correct":          bool(preds[i] == labels[i]),
        })
    return out


# ---------------------------------------------------------------------------
# Blend weight
# ---------------------------------------------------------------------------

def nn_blend_weight(n_train_cases: int) -> float:
    """Weight of NN component in final p_cash blend.

    < 3 cases → 0.0   (NN inactive)
    25  cases → ~0.19  (growing)
    75  cases → ~0.28  (substantial)
    ∞   cases → 0.30   (asymptote)

    The NN learns systematic LLM calibration errors across jurisdictions,
    claim types, and defendant profiles from historical outcomes.
    """
    if n_train_cases < 3:
        return 0.0
    return 0.30 * (1.0 - math.exp(-n_train_cases / 25.0))
