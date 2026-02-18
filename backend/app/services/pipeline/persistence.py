"""Persistence layer for learning parameters and calibration data.

Uses JSON file storage (upgradeable to SQLite/PostgreSQL).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .models import LearningParams

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("PIPELINE_DATA_DIR", "/tmp/eu_claims_pipeline_data"))


class PipelineStore:
    """File-based persistence for pipeline parameters."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or _DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._learning_file = self.data_dir / "learning_params.json"
        self._predictions_file = self.data_dir / "predictions_log.jsonl"

    def load_learning_params(self) -> dict[str, LearningParams]:
        """Load all learning parameters from storage."""
        if not self._learning_file.exists():
            return {}
        try:
            data = json.loads(self._learning_file.read_text())
            return {
                key: LearningParams(**val)
                for key, val in data.items()
            }
        except Exception as e:
            logger.warning("Failed to load learning params: %s", e)
            return {}

    def save_learning_params(self, store: dict[str, LearningParams]) -> None:
        """Save all learning parameters to storage."""
        try:
            data = {
                key: val.model_dump()
                for key, val in store.items()
            }
            self._learning_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.warning("Failed to save learning params: %s", e)

    def log_prediction(
        self,
        case_id: str,
        p_obsiegen: float,
        p_eintreibung: float | None,
        context_key: str,
    ) -> None:
        """Log a prediction for later calibration analysis."""
        try:
            entry = json.dumps({
                "case_id": case_id,
                "p_obsiegen": p_obsiegen,
                "p_eintreibung": p_eintreibung,
                "context_key": context_key,
            })
            with open(self._predictions_file, "a") as f:
                f.write(entry + "\n")
        except Exception as e:
            logger.debug("Failed to log prediction: %s", e)

    def load_predictions(self) -> list[dict]:
        """Load prediction log for calibration."""
        if not self._predictions_file.exists():
            return []
        predictions = []
        try:
            for line in self._predictions_file.read_text().splitlines():
                if line.strip():
                    predictions.append(json.loads(line))
        except Exception:
            pass
        return predictions
