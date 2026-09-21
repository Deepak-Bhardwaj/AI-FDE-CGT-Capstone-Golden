"""FastAPI routes for the supply-chain digital twin and bounded logistics self-heal."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cgt_orchestrator.intelligence.digital_twin import RULE_VERSION, build_twin_state, swarm_script
from cgt_orchestrator.intelligence.self_heal_store import apply_self_heal, audit_log, overlay_for
from cgt_orchestrator.paths import db_path

router = APIRouter(prefix="/api")


class HealBody(BaseModel):
    actor: str = Field(default="logistics-agent", max_length=120)


def _shipment(shipment_id: str, database_path: str | None = None) -> dict[str, Any] | None:
    con = sqlite3.connect(str(database_path or db_path()))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM shipments WHERE shipment_id = ?",
            (shipment_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


@router.get("/digital-twin/state")
def digital_twin_state(limit: int = 48):
    """Network graph of centers, plants, couriers and active cryo legs."""
    return build_twin_state(limit=limit)


@router.get("/agents/swarm-log")
def agent_swarm_log(shipment_id: str = "SHP-R-00610"):
    """Scripted multi-agent transcript for the demo. Not an LLM."""
    row = _shipment(shipment_id)
    healed = overlay_for(shipment_id)
    return {
        "shipment_id": shipment_id,
        "patient_id": (row or {}).get("patient_key"),
        "events": swarm_script(row, healed),
        "rule_version": RULE_VERSION,
        "note": "Simulated agent dialogue from local rules. No model call.",
    }


@router.get("/logistics/audit")
def logistics_audit():
    return {
        "count": len(audit_log()),
        "actions": audit_log(),
        "autonomous_action_scope": "logistics_courier_reroute_only",
    }


@router.post("/logistics/self-heal/{shipment_id}")
def self_heal_shipment(shipment_id: str, body: HealBody | None = None):
    """Courier/ETA overlay for BOOKED or IN_TRANSIT only. Never writes QMS or identity."""
    body = body or HealBody()
    row = _shipment(shipment_id)
    if not row:
        raise HTTPException(404, "shipment not found")
    result = apply_self_heal(row, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(409, result)
    return result
