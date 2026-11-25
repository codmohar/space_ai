"""Evaluation results endpoint serving strictly measured script outputs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas import EvalResultsResponse

router = APIRouter(prefix="/api/eval", tags=["evaluation"])


def load_eval_results(results_path: Path | None = None) -> EvalResultsResponse:
    settings = get_settings()
    path = results_path or settings.eval_results_path
    if not path.exists():
        # Check container mount path /data/evaluation/retrieval_results.json as well
        alt = Path("/data/evaluation/retrieval_results.json")
        if alt.exists():
            path = alt
        else:
            return EvalResultsResponse(status="Not yet evaluated", methods=[])

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EvalResultsResponse.model_validate(payload)
    except Exception:  # noqa: BLE001
        return EvalResultsResponse(status="Not yet evaluated", methods=[])


@router.get("/results", response_model=EvalResultsResponse)
def get_eval_results() -> EvalResultsResponse:
    return load_eval_results()
