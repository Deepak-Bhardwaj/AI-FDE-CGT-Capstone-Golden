"""The Lot Context Pack.

One versioned, structured answer to "what is actually true about this lot right now", assembled
by query from the operational records. It is the only lot truth any advisory layer may ever be
given, so its boundary matters more than its contents: identity is looked up by identifier, not
retrieved by similarity, and nothing identifying is ever placed in it.

Two properties are load-bearing and are enforced by test rather than convention:

  - No identifying field - name, date of birth, MRN - can appear in a pack. patient_ref is a
    pseudonymous key.
  - canonical_state is this service's own position, not a restatement of any one source. Where
    the sources disagree the disagreement is carried in conflicts[] and the state stays
    conservative, because a pack that repeated whichever system was most optimistic would be
    worse than no pack at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import gates, identity, sop
from .loader import Estate, load
from .reality import BLOCKING_QC, reconstruct

PACK_VERSION = "1.0"

# The five states the target specification names, plus two that precede them. The spec's
# vocabulary starts at QC; a lot exists before that and must still have somewhere to be.
CANONICAL_STATES = ("awaiting_collection", "in_manufacture", "qc_attached", "on_hold",
                    "pending_disposition", "released", "rejected")

# Anything that could carry identity out of the operational store and into a pack. A bare
# "name" is deliberately absent: this codebase uses it for gates, centres, roles and models,
# never for a patient, and a guard that cries wolf is one people learn to ignore. Every field
# that does carry a person's name is listed explicitly.
FORBIDDEN_FIELDS = frozenset({
    "full_name", "patient_name", "synthetic_name", "given_name", "family_name",
    "dob", "date_of_birth", "birth_date", "mrn", "medical_record_number", "ssn", "nhs_number",
    "address", "postcode", "phone", "email",
})

# Any MES state meaning the plant has finished. None of them is a quality disposition.
MANUFACTURING_FINISHED = frozenset({"RELEASED", "MFG_COMPLETE", "COMPLETE", "COMPLETED"})


class LotNotFound(KeyError):
    """Raised when no lot resolves from the supplied identifier."""


@dataclass(frozen=True)
class LotRef:
    patient_key: str
    batch: dict[str, Any] | None

    @property
    def lot_id(self) -> str | None:
        return self.batch["batch_id"] if self.batch else None


def resolve(lot_id: str, est: Estate) -> LotRef:
    """Accepts a lot identifier, or a patient key for a lot that does not exist yet."""
    for batch in est.batches:
        if batch["batch_id"] == lot_id:
            return LotRef(batch["patient_key"], batch)
    if lot_id in est.by_key:
        batches = est.batches_by_key.get(lot_id) or []
        return LotRef(lot_id, batches[-1] if batches else None)
    raise LotNotFound(lot_id)


def _timestamp(row: dict, *names: str) -> str | None:
    for name in names:
        value = (row or {}).get(name)
        if value:
            return value
    return None


def _side(source: str, value: Any, observed_at: str | None = None) -> dict:
    return {"source": source, "value": value, "observed_at": observed_at}


def conflicts_for(ref: LotRef, est: Estate) -> list[dict]:
    """Both values, both sources, both timestamps. Never one collapsed answer."""
    out: list[dict] = []
    batch, key = ref.batch, ref.patient_key

    if batch:
        observed = _timestamp(batch, "mfg_end", "mfg_start")
        mes, erp, qms = batch["mes_status"], batch["erp_status"], batch["qms_release_status"]
        if mes in MANUFACTURING_FINISHED and qms != "RELEASED":
            out.append({"field": "release", "left": _side("MES", mes, observed),
                        "right": _side("QMS", qms, observed),
                        "note": "Manufacturing completion is not product release."})
        if erp == "AVAILABLE" and qms != "RELEASED":
            out.append({"field": "release", "left": _side("ERP", erp, observed),
                        "right": _side("QMS", qms, observed),
                        "note": "Availability in ERP is not a quality disposition."})

    for slot in est.slots_by_key.get(key, []):
        if slot["scheduler_state"] != slot["mes_state"]:
            out.append({"field": "slot", "left": _side("SCHEDULER", slot["scheduler_state"],
                                                       slot.get("scheduled_start")),
                        "right": _side("MES", slot["mes_state"], slot.get("scheduled_start")),
                        "note": f"Slot {slot['slot_id']} is described differently by each system."})

    assessment = identity.assess(key, est)
    # Each side's value is keyed by the field it describes, so the ordinary field-sensitivity
    # redaction removes a date of birth from a role that may not see one. A conflict whose two
    # values were both "see the queue" would not be a conflict surface at all.
    observed: dict[str, dict[str, Any]] = {}
    for evidence in assessment.evidence:
        if evidence.fact.startswith("identity."):
            observed.setdefault(evidence.fact.split(".", 1)[1], {})[evidence.source] = evidence.value
    for conflict in assessment.conflicts:
        name = conflict.split(":")[0].strip()
        sides = observed.get(name)
        if sides and len(sides) >= 2:
            sources = sorted(sides)
            out.append({"field": f"identity.{name}",
                        "left": _side(sources[0], {name: sides[sources[0]]}),
                        "right": _side(sources[1], {name: sides[sources[1]]}),
                        "note": conflict})
        else:
            out.append({"field": f"identity.{name}" if name.isidentifier() else "identity.record",
                        "left": _side("IDENTITY_SCAN", {"finding": conflict}),
                        "right": _side("PATIENT_REGISTER", {"finding": "one patient, one key"}),
                        "note": conflict})

    coi_ids = {c["coi_id"] for c in est.collections_by_key.get(key, []) if c.get("coi_id")}
    if batch and batch.get("coi_id"):
        coi_ids.add(batch["coi_id"])
    if len(coi_ids) > 1:
        ordered = sorted(coi_ids)
        out.append({"field": "coi_id", "left": _side("COLLECTION", ordered[0]),
                    "right": _side("MES", ordered[-1]),
                    "note": "More than one chain-of-identity reference is attached to this lot."})
    return out


def qc_for(ref: LotRef, est: Estate) -> list[dict]:
    """Every required assay appears. An unreported one says MISSING rather than being absent."""
    rows = est.qc_by_batch.get(ref.lot_id or "", []) if ref.lot_id else []
    reported = {row["assay"]: row for row in rows}
    out = []
    for assay in sorted(gates.REQUIRED_ASSAYS):
        row = reported.get(assay)
        if row is None:
            out.append({"assay": assay, "disposition": "MISSING", "value": None, "unit": None,
                        "event_id": None, "reported_at": None})
            continue
        out.append({"assay": assay, "disposition": row["result"], "value": row.get("value") or None,
                    "unit": row.get("unit") or None, "event_id": row["qc_id"],
                    "reported_at": row.get("reported_at") or None})
    for assay, row in sorted(reported.items()):
        if assay not in gates.REQUIRED_ASSAYS:
            out.append({"assay": assay, "disposition": row["result"], "value": row.get("value") or None,
                        "unit": row.get("unit") or None, "event_id": row["qc_id"],
                        "reported_at": row.get("reported_at") or None, "required": False})
    return out


def holds_for(ref: LotRef, est: Estate, assessment) -> list[dict]:
    """Structured blockers. An empty list means an empty brief, not a story."""
    out: list[dict] = []
    for deviation in est.deviations_by_key.get(ref.patient_key, []):
        if (deviation.get("status") or "").upper() in {"CLOSED", "RESOLVED"}:
            continue
        out.append({"code": f"DEVIATION_{deviation.get('severity', 'UNKNOWN')}",
                    "source": "QMS", "occurred_at": deviation.get("opened_at"),
                    "reference": deviation.get("deviation_id"),
                    "detail": f"{deviation.get('type', 'Deviation')} is {deviation.get('status', 'open')}."})

    for shipment in est.shipments_by_key.get(ref.patient_key, []):
        if (shipment.get("temp_excursion") or "").strip().upper() == "TRUE":
            out.append({"code": "TEMP_EXCURSION_FLAGGED", "source": "TMS",
                        "occurred_at": shipment.get("arrived_at") or shipment.get("departed_at"),
                        "reference": shipment["shipment_id"],
                        "detail": "Logistics flagged a temperature excursion on this shipment."})

    for gate in assessment.gates:
        if gate.status in gates.OPEN:
            out.append({"code": f"GATE_{gate.gate_id}_{gate.status.value}", "source": "POLICY",
                        "occurred_at": None, "reference": gate.gate_id, "detail": gate.reason})
    return out


def events_for(ref: LotRef, est: Estate, limit: int | None = None) -> list[dict]:
    """Event time and recording time are different facts and are kept apart."""
    rows = est.timeline(ref.patient_key)
    if limit is not None:
        rows = rows[-limit:] if limit else []
    return [{"event_id": row["event_id"], "type": row["event_type"],
             "occurred_at": row.get("occurred_at") or None,
             "recorded_at": row.get("recorded_at") or None,
             "source": row.get("source") or None,
             "batch_id": row.get("batch_id") or None} for row in rows]


def canonical_state(ref: LotRef, journey, assessment, holds: list[dict],
                    qc: list[dict]) -> tuple[str, str]:
    """This service's own position, with the reason it holds it."""
    batch = ref.batch
    qms = (batch or {}).get("qms_release_status", "")

    if batch is None:
        collected = bool(journey.value("collection.coi"))
        return ("in_manufacture" if collected else "awaiting_collection",
                "No batch record exists for this patient yet.")
    if qms == "REJECTED":
        return "rejected", "Quality has recorded a rejection in the QMS."
    if journey.blocking_reasons or any(h["source"] != "POLICY" for h in holds):
        detail = (journey.blocking_reasons or [h["detail"] for h in holds])[0]
        return "on_hold", detail
    if assessment.readiness is gates.Readiness.CONFLICTED:
        return "on_hold", "Sources disagree about this lot; the disagreement is unresolved."
    if qms == "RELEASED":
        return "released", "Quality has recorded an explicit release in the QMS."
    if any(item["disposition"] == "MISSING" for item in qc):
        return "qc_attached", "Some required tests have not been reported yet."
    if any(item["disposition"] in BLOCKING_QC for item in qc):
        return "on_hold", "At least one required test is unresolved."
    return "pending_disposition", "All required evidence is present and a human decision is due."


def build(lot_id: str, estate: Estate | None = None, event_limit: int | None = 100) -> dict:
    """Assemble the pack by query. This is a lookup, never a search."""
    est = estate or load()
    ref = resolve(lot_id, est)
    key = ref.patient_key
    batch = ref.batch

    journey = reconstruct(key, est)
    assessment = gates.evaluate(key, est, journey)
    identity_view = identity.assess(key, est)

    collections = est.collections_by_key.get(key, [])
    collection = collections[-1] if collections else None
    product_code = (batch or {}).get("product_code") or None
    product = est.product_by_code.get(product_code or "", {})

    conflicts = conflicts_for(ref, est)
    qc = qc_for(ref, est)
    holds = holds_for(ref, est, assessment)
    state, state_reason = canonical_state(ref, journey, assessment, holds, qc)

    return {
        "pack_version": PACK_VERSION,
        "lot_id": ref.lot_id,
        "coi_id": (batch or {}).get("coi_id") or (collection or {}).get("coi_id") or None,
        "patient_ref": key,
        "din": (collection or {}).get("bag_id") or None,
        "collection_id": (collection or {}).get("collection_id") or None,
        "product_code": product_code,
        "process_version": product.get("therapy_family") or None,
        "spec_version": sop.effective("SOP-QA-014").ref,
        "policy_version": gates.POLICY_VERSION,
        "canonical_state": state,
        "canonical_state_reason": state_reason,
        "mes_state": (batch or {}).get("mes_status") or None,
        "erp_state": (batch or {}).get("erp_status") or None,
        "qms_state": (batch or {}).get("qms_release_status") or None,
        "conflicts": conflicts,
        "qc": qc,
        "holds": holds,
        "events": events_for(ref, est, event_limit),
        "identifiers_agree": not identity_view.blocking and not identity_view.conflicts,
        "identity_outcome": identity_view.outcome.value,
        "readiness": assessment.readiness.value,
        "blocking_reasons": list(journey.blocking_reasons),
        "boundary": "Assembled by query from the operational store. Identity is looked up by "
                    "identifier, never retrieved by similarity. No identifying field appears "
                    "here, and nothing in this pack is an authority to act.",
    }


def contains_identifying_fields(payload) -> list[str]:
    """Walks a pack and names any field that should never have reached it."""
    found: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for name, value in node.items():
                here = f"{path}.{name}" if path else name
                if name.lower() in FORBIDDEN_FIELDS:
                    found.append(here)
                walk(value, here)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(payload)
    return found
