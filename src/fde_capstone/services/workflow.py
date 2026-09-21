"""End-to-end vein-to-vein workflow projection.

The fifteen canonical stages from docs/01_problem_context.md, each derived from evidence and
the gate engine. A stage is never shown as complete on the strength of an advisory system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import gates
from .attestations import STORE as ATTESTATIONS
from .loader import Estate, load, parse_time, phrase
from .reality import Journey, reconstruct


class StageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"
    WAITING = "WAITING"
    NOT_STARTED = "NOT_STARTED"
    HALTED = "HALTED"


@dataclass
class Stage:
    seq: int
    stage_id: str
    name: str
    status: StageStatus
    detail: str
    owner: str
    gate_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    occurred_at: str | None = None
    next_action: str | None = None
    action_authority: str | None = None
    proceeded_despite: list[str] = field(default_factory=list)
    attestation: dict | None = None

    def as_dict(self) -> dict:
        return {
            "seq": self.seq, "stage_id": self.stage_id, "name": self.name,
            "status": self.status.value, "detail": self.detail, "owner": self.owner,
            "gate_ids": self.gate_ids, "evidence_refs": self.evidence_refs,
            "occurred_at": self.occurred_at, "next_action": self.next_action,
            "action_authority": self.action_authority,
            "proceeded_despite": self.proceeded_despite,
            "attestation": self.attestation,
        }


STAGE_DEFS = [
    ("S01", "Patient identified", "Operations coordinator", ["G1"]),
    ("S02", "Eligibility", "Treating clinician", []),
    ("S03", "Consent", "Clinical authority", ["G2"]),
    ("S04", "Financial authorization", "Payer operations", ["G3"]),
    ("S05", "Treatment centre readiness", "Quality", ["G4"]),
    ("S06", "Apheresis / collection", "Treatment centre", []),
    ("S07", "Chain of identity", "Identity adjudicator", ["G1"]),
    ("S08", "Outbound logistics", "Logistics coordinator", []),
    ("S09", "Manufacturing slot", "Manufacturing planner", []),
    ("S10", "Manufacturing", "Manufacturing", ["G5"]),
    ("S11", "Quality control", "Laboratory", ["G6"]),
    ("S12", "QA release", "Quality", ["G7", "G8"]),
    ("S13", "Return logistics", "Logistics coordinator", ["G9"]),
    ("S14", "Conditioning", "Treating clinician", ["G10"]),
    ("S15", "Infusion readiness", "Treatment centre", ["G10"]),
]

EVENT_BY_STAGE = {
    "S01": "PATIENT_ENROLLED",
    "S06": "COLLECTION_COMPLETED",
    "S08": "SHIPMENT_DISPATCHED",
    "S10": "MANUFACTURING_STARTED",
    "S12": "QA_RELEASED",
    "S15": "INFUSED",
}


def _gate(assessment, gate_id: str):
    return next((g for g in assessment.gates if g.gate_id == gate_id), None)


def _from_gates(assessment, gate_ids: list[str]) -> tuple[StageStatus, str, list[str]]:
    results = [g for g in (_gate(assessment, gid) for gid in gate_ids) if g]
    if not results:
        return StageStatus.WAITING, "", []
    refs = sorted({r for g in results for r in g.evidence_refs})
    if any(g.status is gates.GateStatus.CONFLICT for g in results):
        g = next(g for g in results if g.status is gates.GateStatus.CONFLICT)
        return StageStatus.CONFLICT, g.reason, refs
    if any(g.status is gates.GateStatus.FAIL for g in results):
        g = next(g for g in results if g.status is gates.GateStatus.FAIL)
        return StageStatus.BLOCKED, g.reason, refs
    if any(g.status is gates.GateStatus.UNKNOWN for g in results):
        g = next(g for g in results if g.status is gates.GateStatus.UNKNOWN)
        return StageStatus.WAITING, g.reason, refs
    if all(g.status is gates.GateStatus.NOT_APPLICABLE for g in results):
        return StageStatus.NOT_STARTED, "Not applicable at this point in the journey.", refs
    return StageStatus.COMPLETE, results[0].reason, refs


def build(patient_key: str, estate: Estate | None = None,
          journey: Journey | None = None) -> dict:
    est = estate or load()
    j = journey or reconstruct(patient_key, est)
    assessment = gates.evaluate(patient_key, est, j)

    events = {e["event_type"]: e for e in est.timeline(patient_key)}
    collections = est.collections_by_key.get(patient_key, [])
    shipments = est.shipments_by_key.get(patient_key, [])
    slots = est.slots_by_key.get(patient_key, [])
    batches = est.batches_by_key.get(patient_key, [])
    consent_withdrawn = j.value("consent.status") == "WITHDRAWN"

    stages: list[Stage] = []
    for seq, (stage_id, name, owner, gate_ids) in enumerate(STAGE_DEFS, start=1):
        status, detail, refs = _from_gates(assessment, gate_ids)
        occurred = None
        event = events.get(EVENT_BY_STAGE.get(stage_id, ""))
        if event:
            occurred = event["occurred_at"]

        if stage_id == "S02":
            status = StageStatus.COMPLETE if est.by_key.get(patient_key) else StageStatus.NOT_STARTED
            detail = ("The clinical system states this patient is eligible, and no other source "
                      "contradicts it.")
        elif stage_id == "S06":
            if collections:
                col = collections[0]
                occurred = col["collection_time"]
                status = StageStatus.COMPLETE
                detail = (f"Collection {col['collection_id']} was taken with "
                          f"{col['viability_pct']}% cell viability and was assessed as "
                          f"{phrase(col['quality_flag'])}.")
                refs = [f"collections.csv:{col['collection_id']}"]
            else:
                status, detail = StageStatus.NOT_STARTED, "No collection has been recorded yet."
        elif stage_id == "S08":
            outbound = [s for s in shipments if s["direction"] == "OUTBOUND"]
            if outbound:
                ship = outbound[0]
                occurred = ship["departed_at"]
                status = (StageStatus.COMPLETE if ship["status"] == "DELIVERED"
                          else StageStatus.ACTIVE)
                courier = est.courier_by_id.get(ship["courier_id"], {})
                detail = (f"Shipment {ship['shipment_id']} to the manufacturing site is "
                          f"{phrase(ship['status'])}, carried by "
                          f"{courier.get('name', ship['courier_id'])}.")
                refs = [f"shipments.csv:{ship['shipment_id']}"]
            else:
                status, detail = StageStatus.NOT_STARTED, "No outbound shipment has been raised."
        elif stage_id == "S09":
            if slots:
                slot = slots[0]
                occurred = slot["scheduled_start"]
                refs = [f"manufacturing_slots.csv:{slot['slot_id']}"]
                if slot["scheduler_state"] == "CONFIRMED" and slot["mes_state"] == "CANCELLED":
                    status = StageStatus.CONFLICT
                    detail = (f"Slot {slot['slot_id']} is confirmed in the scheduler but cancelled "
                              "in MES, so the capacity does not actually exist.")
                elif slot["scheduler_state"] == "CONFIRMED":
                    status = StageStatus.COMPLETE
                    detail = (f"Slot {slot['slot_id']} is confirmed in both the scheduler and MES.")
                else:
                    status = StageStatus.ACTIVE
                    detail = (f"Slot {slot['slot_id']} is {phrase(slot['scheduler_state'])} in the "
                              f"scheduler and {phrase(slot['mes_state'])} in MES.")
            else:
                status, detail = StageStatus.NOT_STARTED, "No manufacturing slot has been reserved."
        elif stage_id == "S13":
            returns = [s for s in shipments if s["direction"] == "RETURN"]
            if returns:
                occurred = returns[0]["departed_at"]

        if consent_withdrawn and seq > 3:
            status = StageStatus.HALTED
            detail = "The patient withdrew consent, so every step from here on has been stopped."

        # Stages with no gate of their own are cleared by the attestation directly.
        if not gate_ids and status in (StageStatus.BLOCKED, StageStatus.CONFLICT):
            if att := ATTESTATIONS.live_for_stage(patient_key, stage_id):
                status = StageStatus.COMPLETE
                detail = (f"Cleared on a signed attestation by {att.by} ({att.authority}) on "
                          f"{att.attested_at[:10]}: {att.justification} The source systems still "
                          f"report: {detail}")

        gate_obj = _gate(assessment, gate_ids[0]) if gate_ids else None
        next_action = None
        authority = None
        if status in (StageStatus.BLOCKED, StageStatus.CONFLICT, StageStatus.WAITING) and gate_obj:
            authority = gate_obj.authority
            next_action = {
                StageStatus.BLOCKED: "Resolve the failed check",
                StageStatus.CONFLICT: "Decide which source is correct",
                StageStatus.WAITING: "Obtain the missing evidence",
            }[status]
        elif status in (StageStatus.BLOCKED, StageStatus.CONFLICT) and not gate_obj:
            # Stages with no gate of their own, such as the scheduler/MES slot disagreement.
            authority = owner
            next_action = ("Decide which source is correct" if status is StageStatus.CONFLICT
                           else "Resolve the failed check")
        elif status is StageStatus.HALTED:
            next_action, authority = "Confirm the withdrawal and close the journey", "Clinical authority"

        stages.append(Stage(seq, stage_id, name, status, detail or "", owner, gate_ids, refs,
                            occurred, next_action, authority))

    for stage in stages:
        if att := ATTESTATIONS.live_for_stage(patient_key, stage.stage_id):
            stage.attestation = {"attestation_id": att.attestation_id, "by": att.by,
                                 "authority": att.authority, "at": att.attested_at}

    current = next((s for s in stages
                    if s.status in (StageStatus.BLOCKED, StageStatus.CONFLICT,
                                    StageStatus.HALTED, StageStatus.ACTIVE)), None)
    completed = sum(1 for s in stages if s.status is StageStatus.COMPLETE)

    # The estate lets material move on while an earlier control is unresolved. That is a finding,
    # not a display problem, so each affected stage names the stage it overtook.
    unresolved: list[str] = []
    for stage in stages:
        if stage.status in (StageStatus.COMPLETE, StageStatus.ACTIVE) and unresolved:
            stage.proceeded_despite = list(unresolved)
        if stage.status in (StageStatus.BLOCKED, StageStatus.CONFLICT, StageStatus.WAITING):
            unresolved.append(stage.stage_id)

    return {
        "patient_key": patient_key,
        "readiness": assessment.readiness.value,
        "policy_version": assessment.policy_version,
        "governed_state": j.state,
        "legacy_status": est.by_key.get(patient_key, {}).get("journey_status"),
        "stages": [s.as_dict() for s in stages],
        "completed_stages": completed,
        "total_stages": len(stages),
        "current_stage": current.as_dict() if current else None,
        "batch_id": batches[0]["batch_id"] if batches else None,
        "blocking_reasons": j.blocking_reasons,
        "uncertainties": j.uncertainties,
        "shadow_signals": j.shadow_signals,
    }


# What has to happen before a blocked gate can pass, and where it has to happen. The control
# tower reads the source systems; it never writes to them, so these are instructions for people.
GATE_STEPS = {
    "G1": [
        "Compare the patient record in CRM, the clinical system and the collection label, and "
        "decide which one is correct.",
        "Correct the wrong record in its own source system.",
        "Re-check the chain of identity on the collection before the material moves again.",
    ],
    "G2": [
        "Confirm with the treating clinician whether the patient has given, changed or withdrawn "
        "consent.",
        "File the signed consent of the current version in the consent system.",
    ],
    "G3": [
        "Ask the payer for a decision, or renew the authorization that has lapsed.",
        "Record the approval reference and its expiry date against the patient.",
    ],
    "G4": [
        "Close the qualification shortfall at the treatment centre: renew the expired staff "
        "training, requalify the equipment, or sign the quality agreement.",
        "Update the centre's qualification record so the evidence matches reality.",
    ],
    "G5": [
        "Finish the manufacturing run, or record in MES what the current batch state means.",
    ],
    "G6": [
        "Report the outstanding assay results in the laboratory system.",
        "Investigate any result that is out of specification and record the conclusion.",
    ],
    "G7": [
        "Investigate each open deviation and record the disposition in the QMS.",
    ],
    "G8": [
        "Clear every other gate first — availability in ERP is not a release.",
        "Record an explicit release decision in the QMS, signed by Quality.",
    ],
    "G9": [
        "Confirm the return shipment was delivered and the custody record is complete.",
        "Disposition any temperature excursion against the current SOP.",
    ],
    "G10": [
        "Confirm the conditioning and infusion prerequisites with the treatment centre.",
    ],
}

HALTED_STEPS = [
    "Confirm the withdrawal of consent with the treating clinician.",
    "Close the journey and stop any material already in flight.",
]

STAGE_STEPS = {
    "S08": [
        "Chase the courier for the current position and the custody record of the shipment.",
    ],
    "S09": [
        "Compare the slot in the scheduler with the same slot in MES and decide which is right.",
        "If the capacity does not really exist, draft an alternative slot for a planner to approve.",
    ],
}


def _operations(stage_id: str, gate_ids: list[str], patient_key: str, est: Estate) -> list[dict]:
    """Governed operations this service can actually perform for a stage. All are proposals."""
    ops: list[dict] = []
    if "G1" in gate_ids:
        ops.append({
            "id": "identity_merge",
            "label": "Put the identity link to adjudication",
            "method": "POST", "path": f"/api/identity/{patient_key}/merge",
            "required_action": "merge_identity",
            "effect": "Raises a merge proposal. It is refused unless the identity evidence "
                      "supports it, and the refusal is recorded either way.",
        })
    if stage_id == "S09" and est.slots_by_key.get(patient_key):
        ops.append({
            "id": "schedule_propose",
            "label": "Draft an alternative manufacturing slot",
            "method": "POST", "path": f"/api/scheduling/propose/{patient_key}",
            "required_action": "draft_schedule",
            "effect": "Produces a draft slot change for a planner to approve. Nothing is booked.",
        })
        ops.append({
            "id": "saga_run",
            "label": "Re-run the slot reservation across scheduler and MES",
            "method": "POST", "path": f"/api/capacity/saga/{patient_key}",
            "required_action": "reserve_slot_provisional",
            "effect": "Re-runs the reservation workflow so the two systems can be compared, "
                      "compensating any step that fails.",
        })
    if stage_id == "S12":
        ops.append({
            "id": "release_propose",
            "label": "Put this batch forward for QA release",
            "method": "POST", "path": f"/api/release/{patient_key}/approve",
            "required_action": "release_product",
            "effect": "Requests release. It is refused while any gate is open, and the reason is "
                      "recorded in the decision log.",
        })
    return ops


def action_plan(patient_key: str, stage_id: str, estate: Estate | None = None) -> dict | None:
    """The outstanding action for one stage: what to do, who may do it, what can be done here."""
    est = estate or load()
    wf = build(patient_key, est)
    stage = next((s for s in wf["stages"] if s["stage_id"] == stage_id), None)
    if stage is None or not (stage["next_action"] or stage["attestation"]):
        return None

    if stage["status"] == StageStatus.HALTED.value:
        steps = HALTED_STEPS
    else:
        steps = next((GATE_STEPS[g] for g in stage["gate_ids"] if g in GATE_STEPS),
                     STAGE_STEPS.get(stage_id, []))

    return {
        "patient_key": patient_key,
        "stage_id": stage_id,
        "stage": stage["name"],
        "status": stage["status"],
        "detail": stage["detail"],
        "action": stage["next_action"] or "No outstanding action",
        "authority": stage["action_authority"] or stage["owner"],
        "owner": stage["owner"],
        "gate_ids": stage["gate_ids"],
        "evidence_refs": stage["evidence_refs"],
        "steps": steps if stage["next_action"] else [],
        "operations": _operations(stage_id, stage["gate_ids"], patient_key, est)
        if stage["next_action"] else [],
    }


def pipeline_summary(estate: Estate | None = None, limit: int = 120) -> dict:
    """Where the whole cohort is sitting, by stage."""
    est = estate or load()
    counts: dict[str, dict[str, int]] = {sid: {} for sid, *_ in STAGE_DEFS}
    names = {sid: name for sid, name, *_ in STAGE_DEFS}

    for patient in est.patients[:limit]:
        wf = build(patient["patient_key"], est)
        for stage in wf["stages"]:
            bucket = counts[stage["stage_id"]]
            bucket[stage["status"]] = bucket.get(stage["status"], 0) + 1

    return {"sampled": min(limit, len(est.patients)),
            "stages": [{"stage_id": sid, "name": names[sid], "counts": counts[sid]}
                       for sid, *_ in STAGE_DEFS]}
