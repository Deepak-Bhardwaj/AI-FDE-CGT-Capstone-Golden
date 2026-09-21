"""FastAPI routes for predictive logistics (POC 3).

Read-only forecasts. Does not dispatch couriers, rebook slots, or release product.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from cgt_orchestrator.intelligence.predictive_logistics import (
    RULE_VERSION,
    predict_delay,
    top_logistics_risks,
)

router = APIRouter(prefix="/api")


@router.get("/predictions/logistics-risk")
def logistics_risk(limit: int = Query(default=10, ge=1, le=50)):
    """Top patients by predicted logistics/manufacturing delay probability."""
    rows = top_logistics_risks(limit=limit)
    return {
        "count": len(rows),
        "predictions": rows,
        "rule_version": RULE_VERSION,
        "autonomous_action": "none",
        "note": (
            "Statistical recommendation from local fixture only. "
            "Does not change courier, slot, QMS, or patient state."
        ),
    }


@router.get("/patients/{patient_id}/delay-prediction")
def delay_prediction(patient_id: str):
    """Explainable delay prediction for one patient."""
    prediction = predict_delay(patient_id)
    if prediction is None:
        raise HTTPException(404, "patient not found")
    return prediction
