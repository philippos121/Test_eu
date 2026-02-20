"""Neural Network API — training and inference endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import NNModel, User
from ..schemas import NNCasePrediction, NNModelRead, NNTrainRequest, NNTrainResponse
import numpy as np

from ..services.nn_service import (
    FEATURE_NAMES,
    collect_training_data,
    extract_features,
    get_all_predictions,
    get_outcome,
    nn_blend_weight,
    train_model,
)

router = APIRouter(prefix="/api/nn", tags=["neural-network"])


async def _require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Nur für Administratoren.")
    return user


# ---------------------------------------------------------------------------
# Status / model info
# ---------------------------------------------------------------------------

@router.get("/status", response_model=Optional[NNModelRead])
async def nn_status(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently active neural network model, or null if none trained."""
    result = await db.execute(
        select(NNModel)
        .where(NNModel.is_active == True)
        .order_by(NNModel.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/history", response_model=List[NNModelRead])
async def nn_history(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return all trained model versions, newest first."""
    result = await db.execute(
        select(NNModel).order_by(NNModel.version.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@router.post("/train", response_model=NNTrainResponse)
async def nn_train(
    req: NNTrainRequest = NNTrainRequest(),
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Train a new neural network model on all completed cases with known outcomes."""
    result = await train_model(
        db,
        epochs=req.epochs,
        lr=req.lr,
        l2=req.l2,
        batch_size=req.batch_size,
    )
    return NNTrainResponse(**result)


# ---------------------------------------------------------------------------
# Predictions on completed cases (for dashboard)
# ---------------------------------------------------------------------------

@router.get("/predictions", response_model=List[NNCasePrediction])
async def nn_predictions(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return NN predictions for all completed cases (actual vs predicted)."""
    preds = await get_all_predictions(db)
    return [NNCasePrediction(**p) for p in preds]


# ---------------------------------------------------------------------------
# Data summary (how many labelled samples exist)
# ---------------------------------------------------------------------------

@router.get("/data-summary")
async def nn_data_summary(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return summary of available training data."""
    _, y, ids, titles = await collect_training_data(db)
    n = len(ids)
    blend_weight = nn_blend_weight(n)

    if n > 0:
        labels = np.argmax(y, axis=1)
        n_class0 = int(np.sum(labels == 0))
        n_class1 = int(np.sum(labels == 1))
        n_class2 = int(np.sum(labels == 2))
    else:
        n_class0 = n_class1 = n_class2 = 0

    return {
        "n_labeled_cases":  n,
        "n_class0":         n_class0,
        "n_class1":         n_class1,
        "n_class2":         n_class2,
        "blend_weight":     round(blend_weight, 4),
        "features":         FEATURE_NAMES,
        "n_features":       len(FEATURE_NAMES),
    }
