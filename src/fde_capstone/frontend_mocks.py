"""Synthetic payloads for the React Control Tower prototype.

These mocks exist so the Vite app can render without a full operational estate.
They are not clinical, Quality, or production records. Arrays are always lists.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

NOW = "2026-09-21T12:00:00Z"


def _iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stage(
    seq: int,
    stage_id: str,
    name: str,
    status: str,
    owner: str,
    gates: list[str],
    *,
    detail: str = "",
    next_action: str | None = None,
    authority: str = "Quality Authority",
) -> dict[str, Any]:
    return {
        "seq": seq,
        "stage_id": stage_id,
        "name": name,
        "status": status,
        "owner": owner,
        "gate_ids": list(gates),
        "detail": detail,
        "occurred_at": NOW if status in {"COMPLETE", "ACTIVE"} else None,
        "evidence_refs": [f"SRC-{stage_id}"] if status != "NOT_STARTED" else [],
        "proceeded_despite": [],
        "handling": None,
        "attestation": None,
        "next_action": next_action,
        "action_authority": authority,
    }


JOURNEY_STAGES = [
    _stage(1, "S01", "Enrolment", "COMPLETE", "Patient Operations", ["G1"], detail="Synthetic enrolment recorded."),
    _stage(2, "S02", "Identity", "CONFLICT", "Identity Authority", ["G1"], detail="CRM and clinical DOB disagree.", next_action="Open identity adjudication", authority="Identity Authority"),
    _stage(3, "S03", "Collection", "COMPLETE", "Treatment centre", ["G4"], detail="Apheresis completed in source MES."),
    _stage(4, "S04", "Inbound logistics", "COMPLETE", "Logistics", ["G9"], detail="Outbound bag delivered."),
    _stage(5, "S05", "Manufacturing", "ACTIVE", "Manufacturing", ["G5"], detail="Batch in process."),
    _stage(6, "S06", "QC packet", "BLOCKED", "Lab / QC", ["G6"], detail="Potency assay still pending.", next_action="Review QC packet"),
    _stage(7, "S07", "Quality release", "BLOCKED", "Quality Authority", ["G8"], detail="QA has not released.", next_action="Open reviewer packet"),
    _stage(8, "S08", "Ready for infusion", "NOT_STARTED", "Clinical", ["G10"], detail="Clinical prerequisites have no source system."),
]


def patient_journey(patient_key: str = "P-00005") -> dict[str, Any]:
    current = next((s for s in JOURNEY_STAGES if s["status"] in {"CONFLICT", "BLOCKED"}), JOURNEY_STAGES[1])
    completed = sum(1 for s in JOURNEY_STAGES if s["status"] == "COMPLETE")
    return {
        "patient_key": patient_key,
        "patient_name": "Casey Chen",
        "batch_id": "BATCH-100",
        "readiness": "BLOCKED",
        "governed_state": "IN_MANUFACTURING",
        "legacy_status": "AVAILABLE",
        "policy_version": "academic-poc",
        "completed_stages": completed,
        "total_stages": len(JOURNEY_STAGES),
        "current_stage": dict(current),
        "stages": [dict(s) for s in JOURNEY_STAGES],
        "steps": [dict(s) for s in JOURNEY_STAGES],
        "journey": [dict(s) for s in JOURNEY_STAGES],
        "scope": "SYNTHETIC_WORKFLOW_MOCK",
    }


def workflow_pipeline() -> dict[str, Any]:
    counts_template = {
        "COMPLETE": 0,
        "ACTIVE": 0,
        "WAITING": 0,
        "BLOCKED": 0,
        "CONFLICT": 0,
        "HALTED": 0,
        "NOT_STARTED": 0,
    }
    stages = []
    for stage in JOURNEY_STAGES:
        counts = dict(counts_template)
        counts[stage["status"]] = 4 if stage["status"] != "NOT_STARTED" else 12
        stages.append({"stage_id": stage["stage_id"], "name": stage["name"], "counts": counts})
    return {"sampled": 50, "stages": stages, "scope": "SYNTHETIC_PIPELINE_MOCK"}


def _predicted(offset_days: int) -> dict[str, str]:
    return {
        "earliest": f"2026-09-{21 + offset_days:02d}T08:00:00Z",
        "expected": f"2026-09-{22 + offset_days:02d}T12:00:00Z",
        "latest": f"2026-09-{24 + offset_days:02d}T18:00:00Z",
    }


def timeline(patient_key: str) -> dict[str, Any]:
    steps = []
    for i, stage in enumerate(JOURNEY_STAGES):
        done = stage["status"] in {"COMPLETE", "ACTIVE"}
        steps.append(
            {
                "stage_id": stage["stage_id"],
                "label": stage["name"],
                "actual_at": NOW if done else None,
                "released": False,
                "elapsed_from_enrolment_h": 24 * i if done else None,
                "predicted": None if done else _predicted(i),
                "expected_hours": 24 * (i + 1),
                "expected_basis": "Median of synthetic cohort",
                "variance_hours": 4 if done else None,
                "note": None,
            }
        )
    projection = {
        "completed_milestones": 4,
        "total_milestones": len(steps),
        "already_complete": False,
        "predicted_completion_label": "Ready for infusion",
        "predicted_completion": _predicted(14),
        "steps": steps,
        "model": {"name": "bounded-fake", "version": "off", "method": "Estate median rolled forward"},
    }
    return {
        "patient_key": patient_key,
        "patient_name": "Casey Chen",
        "centre": "TC-CH-ZRH-01",
        "readiness": "BLOCKED",
        "waiting_on": [
            {"gate_id": "G6", "name": "QC evidence", "authority": "Lab / QC", "status": "BLOCKED"},
            {"gate_id": "G8", "name": "QA release", "authority": "Quality Authority", "status": "BLOCKED"},
        ],
        "advisory": {
            "agent_id": "AG-FORECAST",
            "action_class": "B",
            "confidence": 0.62,
            "generated_at": NOW,
            "summary": "Remaining steps are estimated from synthetic cohort medians. Not an appointment.",
            "uncertainty": "No live capacity or clinical calendar was consulted.",
        },
        "projection": projection,
    }


def planning_projection(start: str = "2026-09-21") -> dict[str, Any]:
    steps = []
    for i, stage in enumerate(JOURNEY_STAGES):
        expected = f"2026-09-{min(28, 21 + i):02d}T12:00:00Z"
        steps.append(
            {
                "stage_id": stage["stage_id"],
                "label": stage["name"],
                "expected": expected,
                "earliest": expected,
                "latest": expected,
                "typical_hours": 24 * (i + 1),
                "days_from_start": {"expected": i + 1, "earliest": i, "latest": i + 2},
                "basis": "Synthetic estate median",
            }
        )
    return {
        "advisory": {
            "agent_id": "AG-JOURNEY",
            "action_class": "B",
            "confidence": 0.58,
            "generated_at": NOW,
            "uncertainty": "Planning aid only. No capacity, payer or clinical check was made.",
        },
        "projection": {
            "start": f"{start}T00:00:00Z",
            "expected_total_days": 14,
            "ready_window": _predicted(14),
            "steps": steps,
            "model": {"name": "bounded-fake", "version": "off", "method": "Rolled-forward estate median"},
        },
    }


def journeys(query: str = "", readiness: str = "", limit: int = 60) -> dict[str, Any]:
    rows = [
        {
            "patient_key": "P-00005",
            "patient_name": "Casey Chen",
            "readiness": "BLOCKED",
            "legacy_status": "AVAILABLE",
            "confidence": 0.55,
            "failed": 2,
            "conflicts": 1,
            "unknown": 1,
            "center_id": "TC-CH-ZRH-01",
            "authority": "Quality Authority",
        },
        {
            "patient_key": "P-00001",
            "patient_name": "Alex Rivera",
            "readiness": "CONFLICTED",
            "legacy_status": "IN_MANUFACTURING",
            "confidence": 0.4,
            "failed": 1,
            "conflicts": 2,
            "unknown": 2,
            "center_id": "TC-US-BOS-01",
            "authority": "Identity Authority",
        },
        {
            "patient_key": "P-00012",
            "patient_name": "Morgan Lee",
            "readiness": "NEEDS_EVIDENCE",
            "legacy_status": "QC_PENDING",
            "confidence": 0.7,
            "failed": 0,
            "conflicts": 0,
            "unknown": 3,
            "center_id": "TC-UK-LON-01",
            "authority": "Lab / QC",
        },
        {
            "patient_key": "P-00018",
            "patient_name": "Jamie Patel",
            "readiness": "BLOCKED",
            "legacy_status": "MFG_COMPLETE",
            "confidence": 0.48,
            "failed": 3,
            "conflicts": 0,
            "unknown": 1,
            "center_id": "TC-DE-FRA-01",
            "authority": "Quality Authority",
        },
    ]
    needle = (query or "").strip().lower()
    if needle:
        rows = [r for r in rows if needle in r["patient_key"].lower() or needle in r["patient_name"].lower()]
    if readiness:
        rows = [r for r in rows if r["readiness"] == readiness]
    return {
        "journeys": rows[: max(1, min(limit, 60))],
        "redacted_fields": [],
        "scope": "SYNTHETIC_JOURNEY_INDEX",
    }


def _gate(gate_id: str, name: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "name": name,
        "status": status,
        "reason": reason,
        "rule_id": f"RULE-{gate_id}",
        "rule_version": "1.0",
        "source_system": "synthetic",
        "rule_statement": reason,
        "fired": f"{gate_id}-FIRE",
        "authority": "Quality Authority" if gate_id in {"G8"} else "Human reviewer",
        "sop_ref": "SOP-QA-014-v4" if gate_id == "G8" else None,
        "advisory": [],
    }


def journey_detail(patient_key: str) -> dict[str, Any]:
    gates = [
        _gate("G1", "Identity", "CONFLICT", "DOB disagrees across CRM and clinical."),
        _gate("G2", "Consent", "PASS", "Consent valid in source."),
        _gate("G3", "Payer", "PASS", "Authorization present."),
        _gate("G4", "Centre", "PASS", "Centre qualified."),
        _gate("G5", "Manufacturing", "PASS", "MES complete."),
        _gate("G6", "QC evidence", "BLOCKED", "Potency pending."),
        _gate("G7", "Deviations", "PASS", "No open deviations."),
        _gate("G8", "QA release", "BLOCKED", "Quality has not released."),
        _gate("G9", "Return custody", "UNKNOWN", "Return not started."),
        _gate("G10", "Clinical prerequisites", "UNKNOWN", "No authoritative source."),
    ]
    return {
        "journey": {
            "patient_key": patient_key,
            "state": "IN_MANUFACTURING",
            "facts": {
                "identity.dob": {"value": "1972-09-18", "resolution": "CONFLICT", "note": "Clinical export differs."},
                "identity.mrn": {"value": "MRN-741568", "resolution": "PASS", "note": None},
                "product.released": {"value": False, "resolution": "BLOCKED", "note": "QA pending."},
                "qc.complete": {"value": False, "resolution": "BLOCKED", "note": "Potency missing."},
            },
            "blocking_reasons": ["QC packet incomplete", "Quality has not released"],
            "uncertainties": ["G10 has no source system in this estate."],
            "shadow_signals": [],
        },
        "readiness": {
            "readiness": "BLOCKED",
            "policy_version": "academic-poc",
            "required_authority": "Quality Authority",
            "recommendation": "Do not treat legacy AVAILABLE as released. Quality retains the decision.",
            "confidence": 0.55,
            "gates": gates,
            "evidence_references": ["patients.csv", "qc_results.csv", "SOP-QA-014-v4"],
        },
        "legacy": {
            "legacy_product_ready": True,
            "batch_id": "BATCH-100",
            "mes_status": "MFG_COMPLETE",
            "erp_status": "AVAILABLE",
            "qms_release_status": "PENDING",
            "note": "Legacy patient_ready() ignores Quality hold.",
        },
        "access": {"role": "quality", "purpose": "review", "redacted_fields": []},
    }


def stage_action(patient_key: str, stage_id: str) -> dict[str, Any]:
    stage = next((s for s in JOURNEY_STAGES if s["stage_id"] == stage_id), JOURNEY_STAGES[1])
    return {
        "patient_key": patient_key,
        "stage_id": stage_id,
        "stage": stage["name"],
        "status": stage["status"],
        "authority": stage["action_authority"],
        "owner": stage["owner"],
        "action": stage["next_action"] or "Review stage",
        "detail": stage["detail"],
        "gate_ids": list(stage["gate_ids"]),
        "you_hold_the_authority": True,
        "your_role": "quality",
        "authorized_role": "quality",
        "authorized_role_label": "Quality Authority",
        "may_withdraw": False,
        "attestation": None,
        "handling": None,
        "steps": [
            "Confirm source evidence in the originating system.",
            "Record the decision here; this tower does not write back to MES/QMS.",
        ],
        "operations": [
            {
                "id": "propose-slot",
                "path": f"/api/scheduling/propose/{patient_key}",
                "permitted": True,
                "label": "Propose a manufacturing slot change",
                "effect": "Creates a proposal. Reserves nothing.",
                "roles": ["manufacturing"],
            }
        ],
        "decisions": [
            {
                "id": "acknowledge",
                "label": "Acknowledge and keep blocked",
                "help": "Records ownership. Does not clear the gate.",
                "permitted": True,
                "clears_gate": False,
                "requires_signature": True,
            }
        ],
        "evidence_refs": list(stage["evidence_refs"]),
        "recorded": [],
    }


def record_decision(patient_key: str, stage_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    return {
        "outcome": "RECORDED",
        "decision": {
            "decision_id": f"DEC-{stage_id}-001",
            "approved_by": "demo-reviewer",
            "decision": body.get("decision", "acknowledge"),
            "rationale": body.get("justification") or "Recorded in the academic demo. Source systems unchanged.",
            "decided_at": _iso(),
            "e_signature": body.get("e_signature") or "",
            "outcome": "RECORDED",
        },
    }


def exceptions(limit: int = 25) -> dict[str, Any]:
    rows = [
        {
            "exception_id": "EXC-001",
            "patient_key": "P-00005",
            "kind": "IDENTITY:DOB_CONFLICT",
            "score": 92,
            "age_hours": 18,
            "owner": "Identity Authority",
            "authority": "Identity Authority",
            "drivers": ["Conflicting DOB", "Infusion window approaching"],
        },
        {
            "exception_id": "EXC-002",
            "patient_key": "P-00001",
            "kind": "QC:PACKET_INCOMPLETE",
            "score": 81,
            "age_hours": 6,
            "owner": "Lab / QC",
            "authority": "Quality Authority",
            "drivers": ["Potency pending", "Legacy AVAILABLE"],
        },
        {
            "exception_id": "EXC-003",
            "patient_key": "P-00012",
            "kind": "LOGISTICS:EXCURSION",
            "score": 70,
            "age_hours": 3,
            "owner": None,
            "authority": "Quality Authority",
            "drivers": ["Sensor above -120 C", "SOP-LOG-007 v7"],
        },
    ]
    return {
        "method": "Ranked by synthetic patient impact. Observe/recommend only.",
        "exceptions": rows[: max(1, min(limit, 40))],
        "count": len(rows),
    }


def capacity() -> dict[str, Any]:
    return {
        "sites": [
            {"site_id": "MFG-US-NJ-01", "name": "New Jersey suite", "country": "US", "suites": 4, "qc_capacity_day": 6, "booked": 5},
            {"site_id": "MFG-JP-01", "name": "Osaka suite", "country": "JP", "suites": 2, "qc_capacity_day": 3, "booked": 2},
        ],
        "phantom_capacity": [
            {"slot_id": "SLOT-00412", "patient_key": "P-00005", "scheduler_state": "CONFIRMED", "mes_state": "CANCELLED"},
        ],
        "shadow_drift_total": 1,
        "shadow_drift": [
            {
                "slot_id": "SLOT-00412",
                "patient_key": "P-00005",
                "system_priority": 2,
                "shadow_priority": 1,
                "planner_note": "Moved in offline spreadsheet",
            }
        ],
    }


def audit_access(limit: int = 40) -> dict[str, Any]:
    entries = [
        {
            "at": NOW,
            "identity": "quality",
            "role": "quality",
            "purpose": "review",
            "action": "read",
            "subject": "P-00005",
            "allowed": True,
        },
        {
            "at": NOW,
            "identity": "patient_ops",
            "role": "patient_ops",
            "purpose": "coordinate",
            "action": "read",
            "subject": "P-00001",
            "allowed": True,
        },
    ]
    return {"total": len(entries), "entries": entries[:limit]}


def audit_decisions(limit: int = 20) -> dict[str, Any]:
    entries = [
        {
            "decision_id": "DEC-DEMO-0001",
            "subject": {"patient_key": "P-00005"},
            "action": "acknowledge_block",
            "action_class": "B",
            "recommendation": "KEEP_BLOCKED",
            "rule": {"sop_id": "SOP-QA-014", "sop_version": "v4"},
            "approved_by": None,
        }
    ]
    return {"total": len(entries), "entries": entries[:limit]}


def scheduling_board(limit: int = 40) -> dict[str, Any]:
    slots = [
        {
            "slot_id": "SLOT-00412",
            "patient_key": "P-00005",
            "site_id": "MFG-US-NJ-01",
            "scheduled_start": NOW,
            "scheduler_state": "CONFIRMED",
            "mes_state": "CANCELLED",
            "priority": 2,
            "shadow_priority": 1,
            "planner_note": "Offline sheet disagrees",
            "conflict": True,
        },
        {
            "slot_id": "SLOT-00420",
            "patient_key": "P-00012",
            "site_id": "MFG-JP-01",
            "scheduled_start": "2026-09-22T08:00:00Z",
            "scheduler_state": "CONFIRMED",
            "mes_state": "READY",
            "priority": 3,
            "shadow_priority": 3,
            "planner_note": None,
            "conflict": False,
        },
    ]
    return {
        "rule": "A slot is confirmed only when scheduler and MES agree. Proposals reserve nothing.",
        "pending_approvals": [
            {
                "proposal_id": "PRP-0001",
                "patient_key": "P-00018",
                "current": {"slot_id": "SLOT-00501", "site_id": "MFG-US-NJ-01"},
                "status": "AWAITING_APPROVAL",
                "idempotency_key": "idem-P-00018-slot",
                "requires_approval": "Manufacturing planner",
            }
        ],
        "slots": slots[:limit],
    }


def propose_slot(patient_key: str) -> dict[str, Any]:
    return {
        "outcome": "PROPOSED",
        "proposal": {
            "proposal_id": f"PRP-{patient_key}",
            "patient_key": patient_key,
            "status": "AWAITING_APPROVAL",
        },
        "decision": {"rationale": "Proposal recorded. No capacity reserved."},
    }


def approve_slot(patient_key: str) -> dict[str, Any]:
    return {
        "outcome": "CONFIRMED",
        "saga": {
            "saga_id": f"SAGA-{patient_key}",
            "state": "SUCCEEDED",
            "correlation_id": f"CORR-{patient_key}",
            "requires_approval": None,
            "steps": [
                {"name": "reserve_scheduler", "state": "SUCCEEDED", "attempts": 1, "error": None},
                {"name": "reserve_mes", "state": "SUCCEEDED", "attempts": 1, "error": None},
            ],
            "exception": None,
            "alternatives": [],
            "outcome": "CONFIRMED",
        },
        "idempotency": {"attempts": 1, "distinct_reservations": 1, "idempotent_replays": 0},
        "dead_letter": [],
    }


def enrolment_reference() -> dict[str, Any]:
    return {
        "centres": [
            {"center_id": "TC-CH-ZRH-01", "name": "Zurich", "country": "CH"},
            {"center_id": "TC-US-BOS-01", "name": "Boston", "country": "US"},
        ],
        "products": [
            {"product_code": "CGT-C3", "name": "CGT construct C3", "indication": "Synthetic demo"},
        ],
    }


_REGISTRY: dict[str, Any] = {
    "may_register": True,
    "may_adjudicate": True,
    "approvals": [],
    "registrations": [
        {
            "registration_id": "PR-00001",
            "full_name": "Riley Stone",
            "mrn": "900000001",
            "center_id": "TC-CH-ZRH-01",
            "planned_enrolment": "2026-09-25",
            "status": "PROVISIONAL",
            "duplicate_candidates": [],
            "registered_by": "patient_ops",
            "registered_at": NOW,
            "decided_by": None,
        }
    ],
}


def enrolment_registry() -> dict[str, Any]:
    return {
        "may_register": True,
        "may_adjudicate": True,
        "approvals": list(_REGISTRY["approvals"]),
        "registrations": [dict(row) for row in _REGISTRY["registrations"]],
    }


def enrol_register(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    rid = f"PR-{len(_REGISTRY['registrations']) + 1:05d}"
    record = {
        "registration_id": rid,
        "full_name": body.get("full_name") or "New patient",
        "mrn": f"9{len(_REGISTRY['registrations']) + 1:08d}",
        "center_id": body.get("center_id") or "TC-CH-ZRH-01",
        "planned_enrolment": body.get("planned_enrolment") or "2026-09-25",
        "status": "PROVISIONAL",
        "duplicate_candidates": [],
        "registered_by": "patient_ops",
        "registered_at": _iso(),
        "decided_by": None,
    }
    _REGISTRY["registrations"].append(record)
    return {
        "registration": record,
        "next_step": "Provisional record created. Reconcile with the clinical system of record before treating as enrolled.",
        "projection": planning_projection(record["planned_enrolment"])["projection"],
    }


def enrol_decide(registration_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    approval_id = f"APR-{registration_id}"
    _REGISTRY["approvals"].append(
        {
            "approval_id": approval_id,
            "subject": registration_id,
            "can_countersign": True,
            "blocked_reason": None,
        }
    )
    return {"outcome": "AWAITING_COUNTERSIGN", "approval_id": approval_id, "payload": payload or {}}


def enrol_countersign(registration_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    for row in _REGISTRY["registrations"]:
        if row["registration_id"] == registration_id:
            row["status"] = "CONFIRMED"
            row["decided_by"] = "identity"
    _REGISTRY["approvals"] = [a for a in _REGISTRY["approvals"] if a["subject"] != registration_id]
    return {"outcome": "CONFIRMED", "registration_id": registration_id, "payload": payload or {}}


def tracking_board(limit: int = 50) -> dict[str, Any]:
    shipments = [
        {
            "shipment_id": "SHP-O-00005",
            "patient_key": "P-00005",
            "direction": "OUTBOUND",
            "status": "IN_TRANSIT",
            "courier": "CryoLink",
            "origin": "ZRH",
            "destination": "EWR",
            "transit_hours": 18.5,
            "ordering_valid": True,
            "sla_hours": 16,
            "sla_breach": True,
            "above_threshold": 1,
            "sensor_trustworthy": True,
            "flagged": True,
            "issue": True,
        },
        {
            "shipment_id": "SHP-R-00012",
            "patient_key": "P-00012",
            "direction": "RETURN",
            "status": "DELIVERED",
            "courier": "CryoLink",
            "origin": "EWR",
            "destination": "ZRH",
            "transit_hours": 14.0,
            "ordering_valid": True,
            "sla_hours": 16,
            "sla_breach": False,
            "above_threshold": 0,
            "sensor_trustworthy": True,
            "flagged": False,
            "issue": False,
        },
    ]
    return {
        "total": 12,
        "shown": len(shipments[:limit]),
        "summary": {
            "in_transit": 3,
            "sla_breaches": 1,
            "with_excursion_readings": 1,
            "impossible_timelines": 0,
            "open_escalations": 1,
        },
        "shipments": shipments[:limit],
    }


def tracking_detail(shipment_id: str) -> dict[str, Any]:
    origin = {"city": "Zurich", "country": "CH", "lat": 47.45, "lon": 8.55}
    destination = {"city": "Newark", "country": "US", "lat": 40.69, "lon": -74.17}
    telemetry = [
        {"timestamp": NOW, "temperature_c": -150.2, "quality": "OK", "above_threshold": False},
        {"timestamp": NOW, "temperature_c": -118.0, "quality": "OK", "above_threshold": True},
        {"timestamp": NOW, "temperature_c": -155.1, "quality": "DEGRADED", "above_threshold": False},
    ]
    return {
        "shipment_id": shipment_id,
        "patient_key": "P-00005",
        "direction": "OUTBOUND",
        "status": "IN_TRANSIT",
        "origin": "ZRH",
        "destination": "EWR",
        "coi_id": "COI-2269209",
        "batch_id": "BATCH-100",
        "departed_at": NOW,
        "arrived_at": None,
        "anomalies": ["One reading above -120 C"],
        "route": {
            "origin": origin,
            "destination": destination,
            "distance_km": 6320,
            "position": {"lat": 51.5, "lon": -20.0, "estimated": True, "fraction": 0.45},
        },
        "sla": {
            "courier_name": "CryoLink",
            "regions": "EU-US",
            "planned_arrival": "2026-09-22T06:00:00Z",
            "sla_hours": 16,
            "ordering_valid": True,
            "transit_hours": 18.5,
            "sla_breach": True,
            "overrun_hours": 2.5,
        },
        "checkpoints": [
            {
                "seq": 1,
                "title": "Collected",
                "note": "Bag sealed",
                "city": "Zurich",
                "country": "CH",
                "lat": 47.45,
                "lon": 8.55,
                "occurred_at": NOW,
                "recorded_at": NOW,
                "ingest_lag_hours": 0.2,
                "elapsed_hours": 0,
                "source": "MES",
                "status": "COMPLETE",
            },
            {
                "seq": 2,
                "title": "In transit",
                "note": None,
                "city": "Over Atlantic",
                "country": "",
                "lat": 51.5,
                "lon": -20.0,
                "occurred_at": NOW,
                "recorded_at": NOW,
                "ingest_lag_hours": 1.0,
                "elapsed_hours": 8,
                "source": "courier",
                "status": "IN_TRANSIT",
            },
        ],
        "telemetry": telemetry,
        "excursion_profile": {
            "above_threshold": 1,
            "above_threshold_trusted": 1,
            "exposure_window_hours": 0.5,
            "max_temp_c": -118.0,
            "flagged_by_logistics": True,
        },
        "excursion_decision": {
            "recommendation": "QA_REVIEW",
            "rationale": "SOP-LOG-007 v7: duration and sensor quality require Quality disposition. Not auto-fail.",
            "action_class": "B",
            "authority_required": "Quality Authority",
            "rule": {"sop_id": "SOP-LOG-007", "sop_version": "v7"},
        },
        "escalations": [{"issue": "TEMPERATURE", "status": "OPEN", "owner": "Logistics"}],
    }


def logistics_excursions() -> dict[str, Any]:
    decisions = [
        {
            "recommendation": "QA_REVIEW_SENSOR_INTEGRITY",
            "subject": {"shipment_id": "SHP-O-00005"},
            "inputs": [
                {
                    "value": {
                        "above_threshold": 1,
                        "above_threshold_trusted": 0,
                        "max_temp_c": -118.0,
                        "exposure_window_hours": 0.5,
                    }
                }
            ],
            "rule": {"sop_id": "SOP-LOG-007", "sop_version": "v7"},
            "authority_required": "Quality Authority",
            "action_class": "B",
        }
    ]
    return {
        "sop": "SOP-LOG-007 v7",
        "superseded": "v6 point-threshold auto-fail is not used.",
        "shipments": 1,
        "decisions": decisions,
    }


_INTAKE: dict[str, Any] = {"records": [], "pending": []}


def intake() -> dict[str, Any]:
    records = [dict(r) for r in _INTAKE["records"]]
    pending = [dict(p) for p in _INTAKE["pending"]]
    return {
        "totals": {
            "uploads": len(records),
            "proposals": sum(len(r.get("proposals") or []) for r in records),
            "pending": len(pending),
            "auto_applied": 0,
        },
        "pending": pending,
        "records": records,
    }


def intake_samples() -> dict[str, Any]:
    return {
        "samples": [
            {"filename": "qc-note.txt", "label": "QC correspondence example", "content": "Potency pending for BAT-100."},
        ]
    }


def intake_upload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    content = str(body.get("content") or "")
    filename = str(body.get("filename") or "upload.txt")
    proposal = {
        "proposal_id": f"IP-{len(_INTAKE['pending']) + 1:04d}",
        "kind": "QC_NOTE",
        "subject": "P-00005",
        "detail": "Untrusted document proposed a QC observation.",
        "authority": "Quality",
        "corroborated": False,
    }
    record = {
        "intake_id": f"IN-{len(_INTAKE['records']) + 1:04d}",
        "filename": filename,
        "kind": "correspondence",
        "injection_detected": "ignore all previous" in content.lower() or "system:" in content.lower(),
        "proposals": [proposal],
        "notes": ["Content is untrusted until a named authority confirms it."],
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "uploaded_by": "demo",
    }
    _INTAKE["records"].append(record)
    _INTAKE["pending"].append(proposal)
    return {"record": record}


def intake_decide(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _INTAKE["pending"] = [p for p in _INTAKE["pending"] if p["proposal_id"] != proposal_id]
    return {
        "proposal": {"proposal_id": proposal_id, "decided_by": "demo-reviewer", "decision": (payload or {}).get("decision")},
    }


def identity_queue(limit: int = 40) -> dict[str, Any]:
    queue = [
        {
            "patient_key": "P-00005",
            "journey_status": "IN_MANUFACTURING",
            "outcome": "CONFLICT",
            "conflicts": ["DOB CRM vs clinical", "MRN collision"],
            "authority": "identity_adjudicator",
        }
    ]
    return {
        "total": len(queue),
        "queue": queue[:limit],
        "coi_proposals": [
            {
                "source_file": "email_011.eml",
                "patient_key": "P-00005",
                "auto_apply": False,
                "excerpt": "Please treat this as the same patient as yesterday's bag.",
                "proposed_state": "MERGED",
                "authority": "Identity Authority",
            }
        ],
    }


def identity_merge(patient_key: str) -> dict[str, Any]:
    return {
        "decision": {
            "rationale": f"{patient_key}: conflicting DOB/MRN cannot be merged automatically. HITL required.",
            "applied": False,
        }
    }


def evidence_documents() -> dict[str, Any]:
    sample = [
        {
            "source_file": "email_011.eml",
            "proposals": [{"kind": "IDENTITY_HINT"}],
            "injection_detected": False,
        },
        {
            "source_file": "probe.txt",
            "proposals": [{"kind": "RELEASE_INSTRUCTION", "auto_apply": False, "requires": "Quality"}],
            "injection_detected": True,
        },
    ]
    return {
        "documents": 12,
        "proposals": 4,
        "auto_applied": 0,
        "side_effects": 0,
        "boundary": "Retrieved text is untrusted. Extraction holds no write tools.",
        "sample": sample,
    }


def evidence_probe(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    text = str((payload or {}).get("body") or "")
    detected = "ignore" in text.lower() or "released immediately" in text.lower()
    proposals = []
    if detected:
        proposals = [{"kind": "RELEASE_INSTRUCTION", "auto_apply": False, "requires": "Quality"}]
    return {
        "explanation": "Detector is a signal, not the control. No write occurred.",
        "side_effects": [],
        "actions_taken": [],
        "result": {
            "injection_detected": detected,
            "proposals": proposals,
        },
    }


def approvals(action: str = "release_product") -> dict[str, Any]:
    return {"action": action, "approvals": []}


def release_approve(patient_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "outcome": "AWAITING_COUNTERSIGN",
        "decision": {
            "approved_by": "first-reviewer",
            "countersigned_by": None,
            "rationale": (payload or {}).get("justification") or "First signature recorded. Nothing released.",
        },
    }


def release_countersign(patient_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "outcome": "EXECUTED",
        "decision": {
            "approved_by": "first-reviewer",
            "countersigned_by": "second-reviewer",
            "rationale": f"Two-person release recorded for {patient_key} in the academic demo only.",
            "payload": payload or {},
        },
    }


def release_reject(patient_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "rejection": {
            "rejection_id": f"REJ-{patient_key}",
            "rationale": (payload or {}).get("rationale") or "Rejected in demo.",
        }
    }


def withdraw_rejection(rejection_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"rejection_id": rejection_id, "withdrawn": True, "reason": (payload or {}).get("reason")}


def withdraw_attestation(attestation_id: str) -> dict[str, Any]:
    return {"attestation_id": attestation_id, "withdrawn": True}


def reviewer_packet(lot_id: str) -> dict[str, Any]:
    gates = journey_detail(lot_id)["readiness"]["gates"]
    return {
        "lot_id": lot_id,
        "assembled_at": NOW,
        "packet_version": "academic-poc",
        "evidence": {
            "identifiers": {
                "patient_ref": lot_id if lot_id.startswith("P-") else "P-00005",
                "batch_id": "BATCH-100",
                "coi_id": "COI-2269209",
            },
            "state": {
                "canonical_state": "pending_disposition",
                "canonical_state_reason": "Quality has not released. QC potency is pending.",
                "mes_state": "MFG_COMPLETE",
                "erp_state": "AVAILABLE",
                "qms_state": "PENDING",
            },
            "qc": [
                {"assay": "potency", "disposition": "PENDING", "value": None, "unit": None, "event_id": None},
                {"assay": "sterility", "disposition": "PASS", "value": "NO_GROWTH", "unit": "", "event_id": "QC-001"},
            ],
            "conflicts": [
                {
                    "field": "release",
                    "left": {"source": "ERP", "value": "AVAILABLE"},
                    "right": {"source": "QMS", "value": "PENDING"},
                    "note": "Availability is not release.",
                }
            ],
            "holds": [{"code": "QA-HOLD", "source": "QMS", "detail": "Awaiting potency."}],
        },
        "verdict": {
            "recommendation": "BLOCK_RELEASE",
            "gates": gates,
            "blocking_reasons": ["QC potency pending", "Quality has not released"],
            "rules_fired": ["G6-FIRE", "G8-FIRE"],
        },
        "provenance": {
            "assembled_from": "Synthetic source assertions and academic rules.",
            "policy_version": "academic-poc",
            "spec_version": "1.2.0",
            "sop": {"sop_id": "SOP-QA-014", "sop_version": "v4"},
            "rule_version": "academic-poc",
            "model": {"name": "none"},
            "mechanism": "Deterministic assembly. No model discretion.",
        },
        "disposition": {
            "awaiting_countersignature": None,
            "standing_rejection": None,
            "rejections": [],
            "yours_to_withdraw": [],
            "may_release": False,
            "may_reject": True,
            "why_not": "Open QC and Quality gates.",
            "note": "Two-person release still required after gates clear.",
            "rejection_note": "",
            "you_are_the_first_approver": False,
        },
    }


def agent_activity(limit: int = 25) -> dict[str, Any]:
    return {
        "activity": [
            {
                "agent_id": "AG-TRIAGE",
                "action_class": "B",
                "subject": "",
                "invoked_at": NOW,
                "summary": "Ranked identity and QC exceptions. No state changed.",
                "confidence": 0.74,
            }
        ][:limit]
    }
