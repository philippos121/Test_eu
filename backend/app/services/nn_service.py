"""Pure-NumPy Mini Neural Network for case outcome prediction.

Architecture : Input(20) → Dense(16, ReLU) → Dense(8, ReLU) → Dense(1, Sigmoid)
Loss         : Binary cross-entropy with L2 regularisation
Optimizer    : Adam (β₁=0.9, β₂=0.999, ε=1e-8)
"""
from __future__ import annotations

import math
import uuid
from typing import Optional
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Case, CaseEvent, CaseEventType, CaseStatus, NNModel

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    "log_claim_amount",    # log10(amount/1000) clipped to [-2, 2]
    "is_cross_border",
    "claimant_is_legal",
    "defendant_is_legal",
    "has_contract",        # keyword match in evidence/description
    "has_delivery",
    "has_invoice",
    "has_dunning",
    "evidence_count",      # 0-4 evidence types, normalised to 0-1
    "def_country_de",
    "def_country_fr",
    "def_country_it",
    "def_country_ee_pl_cz",  # eastern EU
    "def_country_other_eu",
    "claim_lt_2000",       # small claim < 2 000 EUR
    "claim_2k_5k",         # medium claim 2 000–5 000 EUR
    "claim_gt_5k",         # large claim > 5 000 EUR
    "has_quality_dispute",
    "has_insolvency",
    "is_services",         # service contract (not goods)
]

INPUT_DIM   = len(FEATURE_NAMES)   # 20
HIDDEN_DIMS = [16, 8]
ARCHITECTURE = {"input": INPUT_DIM, "hidden": HIDDEN_DIMS, "output": 1}

_EU_EASTERN = {"PL", "CZ", "SK", "HU", "RO", "BG", "EE", "LT", "LV", "HR"}
_EU_ALL = {
    "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR","HU",
    "IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
}


def extract_features(case: Case) -> np.ndarray:
    """Extract a normalised 20-dim feature vector from a Case ORM object."""
    amount = case.claim_amount or 0.0
    log_amount = float(np.clip(math.log10(max(amount, 1.0) / 1000.0), -2.0, 2.0))

    text = " ".join(filter(None, [
        (case.claim_evidence or ""),
        (case.claim_basis    or ""),
        (case.claim_description or ""),
    ])).lower()

    has_contract  = 1.0 if any(w in text for w in
        ["vertrag", "contract", "auftrag", "kaufvertrag", "bestellung"]) else 0.0
    has_delivery  = 1.0 if any(w in text for w in
        ["lieferschein", "delivery", "liefernachweis", "lieferung", "empfangsbestätigung"]) else 0.0
    has_invoice   = 1.0 if any(w in text for w in
        ["rechnung", "invoice", "fällig", "faktur", "zahlungsziel"]) else 0.0
    has_dunning   = 1.0 if any(w in text for w in
        ["mahnung", "dunning", "reminder", "zahlungserinnerung", "fristsetzung"]) else 0.0
    evidence_count = (has_contract + has_delivery + has_invoice + has_dunning) / 4.0

    def_country = (case.defendant_domicile_country or case.defendant_country or "").upper().strip()

    has_quality    = 1.0 if any(w in text for w in
        ["qualit", "mängel", "defect", "beschwerde", "reklamation"]) else 0.0
    has_insolvency = 1.0 if any(w in text for w in
        ["insolv", "bankrupt", "insolvenz", "konkurs", "pleite"]) else 0.0
    is_services    = 1.0 if any(w in text for w in
        ["dienstleist", "service", "wartung", "beratung", "support", "reparatur"]) else 0.0

    is_other_eu = (
        1.0 if def_country in _EU_ALL
        and def_country not in {"DE", "FR", "IT"}
        and def_country not in _EU_EASTERN
        else 0.0
    )

    return np.array([
        log_amount,
        1.0 if case.is_cross_border else 0.0,
        1.0 if case.claimant_is_legal_person else 0.0,
        1.0 if case.defendant_is_legal_person else 0.0,
        has_contract,
        has_delivery,
        has_invoice,
        has_dunning,
        evidence_count,
        1.0 if def_country == "DE" else 0.0,
        1.0 if def_country == "FR" else 0.0,
        1.0 if def_country == "IT" else 0.0,
        1.0 if def_country in _EU_EASTERN else 0.0,
        is_other_eu,
        1.0 if amount < 2_000 else 0.0,
        1.0 if 2_000 <= amount < 5_000 else 0.0,
        1.0 if amount >= 5_000 else 0.0,
        has_quality,
        has_insolvency,
        is_services,
    ], dtype=np.float64)


def get_outcome(events: list[CaseEvent]) -> Optional[float]:
    """Return 1.0 (success) / 0.7 (settled) / 0.0 (failure) / None (unknown)."""
    types = {e.event_type for e in events}
    if CaseEventType.PAYMENT_RECEIVED in types:
        return 1.0
    if CaseEventType.SETTLED in types:
        return 0.7  # partial success
    if CaseEventType.JUDGMENT_LOSS in types or CaseEventType.COLLECTION_FAILED in types:
        return 0.0
    return None


# ---------------------------------------------------------------------------
# Neural network
# ---------------------------------------------------------------------------

class NeuralNet:
    """2-hidden-layer MLP with Adam optimizer.

    Architecture: Input(20) → Dense(16,ReLU) → Dense(8,ReLU) → Dense(1,Sigmoid)
    """

    def __init__(self, hidden_dims: list[int] = HIDDEN_DIMS, seed: int = 42):
        rng = np.random.RandomState(seed)
        dims = [INPUT_DIM] + hidden_dims + [1]
        self.W: list[np.ndarray] = []
        self.b: list[np.ndarray] = []
        for i in range(len(dims) - 1):
            # Xavier / Glorot uniform initialisation
            limit = math.sqrt(6.0 / (dims[i] + dims[i + 1]))
            self.W.append(rng.uniform(-limit, limit, (dims[i], dims[i + 1])))
            self.b.append(np.zeros((1, dims[i + 1])))
        self._reset_adam()

    # --- Adam state ---

    def _reset_adam(self) -> None:
        self.mW = [np.zeros_like(w) for w in self.W]
        self.vW = [np.zeros_like(w) for w in self.W]
        self.mb = [np.zeros_like(b) for b in self.b]
        self.vb = [np.zeros_like(b) for b in self.b]
        self.t: int = 0

    # --- Activations ---

    @staticmethod
    def _relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, x)

    @staticmethod
    def _relu_d(x: np.ndarray) -> np.ndarray:
        return (x > 0.0).astype(np.float64)

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500.0, 500.0)))

    # --- Forward ---

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
        # output layer
        Z_out = A @ self.W[-1] + self.b[-1]
        y_hat = self._sigmoid(Z_out)
        Z_list.append(Z_out)
        A_list.append(y_hat)
        return y_hat, Z_list, A_list

    def predict(self, X: np.ndarray) -> np.ndarray:
        y_hat, _, _ = self.forward(X)
        return y_hat

    # --- Training ---

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
        """One full pass over the data using mini-batch Adam. Returns mean BCE loss."""
        n = X.shape[0]
        idx = np.random.permutation(n)
        X_s, y_s = X[idx], y[idx]
        total_loss = 0.0
        n_batches = 0

        for start in range(0, n, batch_size):
            Xb = X_s[start:start + batch_size]
            yb = y_s[start:start + batch_size]
            m = Xb.shape[0]

            # Forward
            y_hat, Z_list, A_list = self.forward(Xb)

            # BCE loss (for monitoring)
            loss = -np.mean(
                yb * np.log(y_hat + 1e-12) + (1 - yb) * np.log(1 - y_hat + 1e-12)
            )
            total_loss += loss
            n_batches += 1

            # Backward
            # Output-layer gradient: d(BCE)/d(Z_out) = (y_hat - y)/m
            # (combined gradient through sigmoid + BCE loss)
            dZ = (y_hat - yb) / m   # shape (m, 1)

            self.t += 1

            for i in reversed(range(len(self.W))):
                A_prev = A_list[i]             # (m, d_in)
                dW = A_prev.T @ dZ + l2 * self.W[i]
                db = np.sum(dZ, axis=0, keepdims=True)

                # Adam update
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

                # Propagate gradient to previous layer (skip at input layer)
                if i > 0:
                    dA_prev = dZ @ self.W[i].T           # (m, d_in)
                    dZ = dA_prev * self._relu_d(Z_list[i - 1])  # (m, d_in)

        return total_loss / max(n_batches, 1)

    # --- Serialise / deserialise ---

    def to_dict(self) -> dict:
        return {
            "hidden_dims": HIDDEN_DIMS,
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

    Returns (X, y, case_ids, case_titles).
    X: (n, INPUT_DIM), y: (n, 1).
    """
    cases_result = await db.execute(
        select(Case).where(Case.status == CaseStatus.COMPLETED)
    )
    cases = cases_result.scalars().all()

    X_list: list[np.ndarray] = []
    y_list: list[list[float]] = []
    ids: list[str] = []
    titles: list[str] = []

    for case in cases:
        ev_result = await db.execute(
            select(CaseEvent).where(CaseEvent.case_id == case.id)
        )
        events = ev_result.scalars().all()
        outcome = get_outcome(events)
        if outcome is None:
            continue
        X_list.append(extract_features(case))
        y_list.append([outcome])
        ids.append(str(case.id))
        titles.append(case.title)

    if not X_list:
        return (
            np.zeros((0, INPUT_DIM)),
            np.zeros((0, 1)),
            [],
            [],
        )
    return np.array(X_list), np.array(y_list), ids, titles


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

    # Train / validation split
    rng = np.random.RandomState(seed)
    idx = rng.permutation(n)
    val_size = max(1, int(n * val_split))
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
            val_pred = net.predict(X_val)
            val_loss = float(-np.mean(
                y_val * np.log(val_pred + 1e-12)
                + (1 - y_val) * np.log(1 - val_pred + 1e-12)
            ))
            val_acc = float(np.mean((val_pred >= 0.5) == y_val))
            tr_pred  = net.predict(X_train)
            tr_acc   = float(np.mean((tr_pred >= 0.5) == y_train))
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
    train_acc  = float(np.mean((train_pred >= 0.5) == y_train))
    val_acc    = float(np.mean((val_pred   >= 0.5) == y_val))

    # Feature importance: mean |first-layer weight| per input feature
    importance_raw = np.mean(np.abs(net.W[0]), axis=1).tolist()
    # Sort descending
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

    # Version counter
    all_models = (await db.execute(select(NNModel))).scalars().all()
    version = max((m.version for m in all_models), default=0) + 1

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
        "message":        f"Modell v{version} auf {len(train_idx)} Fällen trainiert.",
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

    Returns (p_nn_raw, meta_dict) or (None, None) if no active model.
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

    net = NeuralNet.from_dict(nn_row.weights)
    X = extract_features(case).reshape(1, -1)
    p_raw = float(net.predict(X)[0, 0])

    w = nn_blend_weight(nn_row.n_train_cases)
    meta = {
        "p_nn_raw":       round(p_raw, 4),
        "nn_weight":      round(w, 4),
        "n_train_cases":  nn_row.n_train_cases,
        "model_version":  nn_row.version,
        "val_accuracy":   nn_row.val_accuracy,
    }
    return p_raw, meta


async def get_all_predictions(db: AsyncSession) -> list[dict]:
    """Return NN predictions for all completed cases (for dashboard display)."""
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
    X, y, ids, titles = await collect_training_data(db)
    if len(ids) == 0:
        return []

    preds = net.predict(X)
    out = []
    for i, (case_id, title) in enumerate(zip(ids, titles)):
        p_nn = float(preds[i, 0])
        actual = float(y[i, 0])
        out.append({
            "case_id":       case_id,
            "case_title":    title,
            "p_nn":          round(p_nn, 4),
            "actual_outcome": actual,
            "correct":       (p_nn >= 0.5) == (actual >= 0.5),
        })
    return out


# ---------------------------------------------------------------------------
# Blend weight
# ---------------------------------------------------------------------------

def nn_blend_weight(n_train_cases: int) -> float:
    """Weight of NN component in final p_cash blend.

    0 training cases → 0.0
    5  cases         → ~0.06
    25 cases         → ~0.19
    100 cases        → ~0.29
    Asymptotes to 0.30 with many cases.
    """
    if n_train_cases < 3:
        return 0.0
    return 0.30 * (1.0 - math.exp(-n_train_cases / 25.0))
