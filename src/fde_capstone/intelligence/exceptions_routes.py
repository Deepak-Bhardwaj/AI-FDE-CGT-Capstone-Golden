"""FastAPI routes for exception intelligence (POC 2).

Observe / correlate / recommend only. POST acknowledge is a HITL receipt,
not a write to MES, QMS, CRM, or the patient record.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cgt_orchestrator.intelligence.acknowledge_store import acknowledge, overlay
from cgt_orchestrator.intelligence.exception_detector import (
    RULE_VERSION,
    detect_exceptions,
    detect_for_patient,
)
from cgt_orchestrator.repository import LegacyRepository

router = APIRouter(prefix="/api")
repo = LegacyRepository()


class AcknowledgeBody(BaseModel):
    actor: str = Field(default="demo-operator", max_length=120)
    note: str = Field(default="", max_length=500)


def _active_payload() -> dict[str, Any]:
    rows = overlay(detect_exceptions())
    open_rows = [row for row in rows if not row.get("acknowledged")]
    return {
        "count": len(rows),
        "unacknowledged_count": len(open_rows),
        "exceptions": rows,
        "rule_version": RULE_VERSION,
        "autonomous_action": "none",
        "note": "Recommendations only. Does not change patient, batch, QMS, or shipment state.",
    }


@router.get("/exceptions/active")
def active_exceptions():
    """Ranked cross-system contradictions with evidence and HITL flags."""
    return _active_payload()


@router.get("/patients/{patient_id}/journey")
def patient_journey_with_blockers(patient_id: str):
    """Journey reconstruction plus exception blockers for one patient."""
    data = repo.journey(patient_id)
    if not data["patient"]:
        raise HTTPException(404, "patient not found")
    blockers = overlay(detect_for_patient(patient_id))
    return {
        **data,
        "blockers": blockers,
        "requires_human_review": any(row.get("requires_human_review") for row in blockers),
        "rule_version": RULE_VERSION,
        "autonomous_action": "none",
    }


@router.post("/exceptions/{exception_id}/acknowledge")
def acknowledge_exception(exception_id: str, body: AcknowledgeBody | None = None):
    """Human-in-the-loop receipt. Does not close deviations or release product."""
    body = body or AcknowledgeBody()
    known = {row["exception_id"] for row in detect_exceptions()}
    if exception_id not in known:
        raise HTTPException(404, "exception not found")
    record = acknowledge(exception_id, actor=body.actor, note=body.note)
    return {
        **record,
        "warning": "HITL acknowledgement only; systems of record are unchanged.",
    }
