"""Compensating actions.

You cannot roll back a collected bag. When something goes wrong on a patient-specific lot the
recovery is never to undo it and never to make another one - it is to hold the plant window,
tell the site, and open a deviation so quality owns the record. Those three are the whole
vocabulary, and the things that are *not* in it matter as much as the things that are.

Cloning or reassigning a lot is refused by name rather than merely absent, because absence is
what lets it get added later by someone solving a delivery problem at two in the morning.

Nothing here reaches an external system. A notification is drafted for a named human to send;
a deviation is staged for filing in the QMS. The external half is gated by the plant guard and
is currently, deliberately, refused. What this module does own is the record: an append-only,
hash-chained account of what was decided, by whom, and why.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import plant_guard
from .audit import EVIDENCE, HashChain
from .loader import Estate, load

RUNBOOK_VERSION = "COMPENSATION-1.0"
LEDGER_PATH = EVIDENCE / "compensations.jsonl"


class CompensationRefused(PermissionError):
    """Raised when a recovery is not one this service will perform."""


# The only recoveries that exist. Each names the role that owns it and what it does not do.
ACTIONS: dict[str, dict] = {
    "HOLD_SLOT": {
        "label": "Hold the manufacturing slot",
        "role": "manufacturing_planner",
        "authority": "Manufacturing planner",
        "intent": "Stop the plant window being given away while the exception is worked.",
        "reversible": True,
        "external_system": None,
        "does_not": "Does not cancel the batch and does not release the patient's material.",
    },
    "NOTIFY_SITE": {
        "label": "Notify the treatment centre",
        "role": "ops_coordinator",
        "authority": "Operations coordinator",
        "intent": "Tell the site early enough that they can stop preparing the patient.",
        "reversible": False,
        "external_system": "SITE_COMMS",
        "does_not": "Does not send anything by itself. A named human sends the message.",
    },
    "OPEN_DEVIATION": {
        "label": "Open a deviation",
        "role": "quality_reviewer",
        "authority": "Quality",
        "intent": "Put the event under quality ownership with an auditable record.",
        "reversible": False,
        "external_system": "QMS",
        "does_not": "Does not classify severity or close the deviation. Quality does that.",
    },
}

# Refused by name. An absent option is one somebody adds later; a named refusal is a decision.
FORBIDDEN_RECOVERIES: dict[str, str] = {
    "CLONE_LOT": "A patient-specific lot cannot be cloned. The starting material is this "
                 "patient's and cannot be manufactured twice from nothing.",
    "REASSIGN_BATCH": "A batch cannot be reassigned to another patient. That is the "
                      "wrong-patient never-event.",
    "ROLLBACK_COLLECTION": "A collection cannot be rolled back. The bag exists.",
    "REISSUE_COI": "A chain-of-identity reference cannot be reissued to escape a conflict. "
                   "Conflicts are adjudicated, not renamed.",
}

LEDGER = HashChain(LEDGER_PATH)


class CompensationState:
    OPEN = "OPEN"
    RELEASED = "RELEASED"
    DISPATCH_PENDING = "DISPATCH_PENDING"


@dataclass
class Compensation:
    compensation_id: str
    lot_id: str | None
    patient_ref: str
    action: str
    reason: str
    by: str
    role: str
    at: str
    state: str
    external_system: str | None = None
    external_dispatch: dict = field(default_factory=dict)
    released_at: str | None = None
    released_by: str | None = None
    released_reason: str | None = None

    def as_dict(self) -> dict:
        spec = ACTIONS[self.action]
        return {"compensation_id": self.compensation_id, "lot_id": self.lot_id,
                "patient_ref": self.patient_ref, "action": self.action,
                "label": spec["label"], "authority": spec["authority"],
                "reason": self.reason, "by": self.by, "role": self.role, "at": self.at,
                "state": self.state, "reversible": spec["reversible"],
                "does_not": spec["does_not"], "external_system": self.external_system,
                "external_dispatch": self.external_dispatch,
                "released_at": self.released_at, "released_by": self.released_by,
                "released_reason": self.released_reason,
                "runbook_version": RUNBOOK_VERSION}


_OPEN: dict[str, Compensation] = {}


def _load_open() -> None:
    for payload in LEDGER.payloads():
        record = {k: v for k, v in payload.items()
                  if k in Compensation.__dataclass_fields__}
        try:
            entry = Compensation(**record)
        except TypeError:
            continue
        if entry.state == CompensationState.RELEASED:
            _OPEN.pop(entry.compensation_id, None)
        else:
            _OPEN[entry.compensation_id] = entry


_load_open()


def _new_id(lot_id: str | None, action: str, by: str) -> str:
    raw = f"{lot_id}|{action}|{by}|{datetime.now(timezone.utc).isoformat()}"
    return "CMP-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dispatch_status(system: str | None) -> dict:
    """Whether the external half could happen. Today it cannot, and says so."""
    if system is None:
        return {"required": False,
                "status": "NOT_REQUIRED",
                "detail": "This action is recorded here and needs no external system."}
    report = plant_guard.evaluate()
    if report.permitted and system in report.systems:
        return {"required": True, "status": "PERMITTED", "system": system,
                "detail": "A signed manifest authorises this system."}
    return {"required": True, "status": "REFUSED", "system": system,
            "detail": f"No external write to {system} is permitted. {report.reason} "
                      "A named human must carry this out and record that they did."}


def apply(lot_id: str | None, patient_ref: str, action: str, reason: str, by: str,
          role: str, estate: Estate | None = None) -> Compensation:
    """Record a compensating action. Refuses anything that would undo or duplicate the lot."""
    est = estate or load()

    if action in FORBIDDEN_RECOVERIES:
        raise CompensationRefused(FORBIDDEN_RECOVERIES[action])
    spec = ACTIONS.get(action)
    if spec is None:
        raise CompensationRefused(
            f"'{action}' is not a recovery this service performs. The vocabulary is "
            f"{', '.join(sorted(ACTIONS))}.")
    if role != spec["role"]:
        raise CompensationRefused(
            f"'{action}' is owned by {spec['authority']}; '{role}' may not perform it.")
    if len((reason or "").strip()) < 10:
        raise CompensationRefused(
            "A compensating action needs a reason of at least 10 characters. It becomes part "
            "of the deviation record.")
    if patient_ref not in est.by_key:
        raise CompensationRefused(f"'{patient_ref}' is not a patient in the register.")

    entry = Compensation(
        compensation_id=_new_id(lot_id, action, by), lot_id=lot_id, patient_ref=patient_ref,
        action=action, reason=reason.strip(), by=by, role=role, at=_now(),
        state=CompensationState.OPEN if spec["reversible"] else CompensationState.DISPATCH_PENDING,
        external_system=spec["external_system"],
        external_dispatch=_dispatch_status(spec["external_system"]))
    _OPEN[entry.compensation_id] = entry
    LEDGER.append("compensation", entry.as_dict())
    return entry


def release(compensation_id: str, by: str, role: str, reason: str) -> Compensation:
    """Lift a reversible compensation. Irreversible ones stay on the record."""
    entry = _OPEN.get(compensation_id)
    if entry is None:
        raise CompensationRefused(f"No open compensation is recorded as '{compensation_id}'.")
    spec = ACTIONS[entry.action]
    if not spec["reversible"]:
        raise CompensationRefused(
            f"'{entry.action}' cannot be lifted. {spec['does_not']} Record what happened next "
            "as a new event instead.")
    if role != spec["role"]:
        raise CompensationRefused(
            f"Only {spec['authority']} may lift '{entry.action}'.")
    if len((reason or "").strip()) < 10:
        raise CompensationRefused("Lifting a compensation needs a reason of at least 10 characters.")

    entry.state = CompensationState.RELEASED
    entry.released_at = _now()
    entry.released_by = by
    entry.released_reason = reason.strip()
    LEDGER.append("compensation", entry.as_dict())
    _OPEN.pop(compensation_id, None)
    return entry


def open_for(patient_ref: str) -> list[dict]:
    return [entry.as_dict() for entry in _OPEN.values() if entry.patient_ref == patient_ref]


def history(patient_ref: str | None = None, limit: int = 50) -> list[dict]:
    rows = LEDGER.recent(limit * 4)
    if patient_ref:
        rows = [row for row in rows if row.get("patient_ref") == patient_ref]
    return rows[:limit]


def runbook() -> dict:
    """The operator runbook, as data rather than prose nobody opens during an incident."""
    return {
        "runbook_version": RUNBOOK_VERSION,
        "principle": "You cannot roll back a collected bag. Recovery is a compensating action, "
                     "never an undo and never a second lot.",
        "actions": [{"action": name, **spec} for name, spec in ACTIONS.items()],
        "refused": [{"action": name, "reason": why}
                    for name, why in FORBIDDEN_RECOVERIES.items()],
        "scenarios": [
            {"situation": "The manufacturing slot will be missed",
             "sequence": ["HOLD_SLOT", "NOTIFY_SITE"],
             "note": "Hold first. A released window is gone and the next one may be weeks away."},
            {"situation": "A temperature excursion is flagged in transit",
             "sequence": ["HOLD_SLOT", "OPEN_DEVIATION"],
             "note": "Quality dispositions the excursion. Nothing about the material is "
                     "decided by holding the slot."},
            {"situation": "Manufacturing fails on a patient-specific lot",
             "sequence": ["OPEN_DEVIATION", "NOTIFY_SITE"],
             "note": "Recovery restarts from collection with clinical agreement. It never "
                     "clones the lot identifier."},
            {"situation": "An identity conflict is found at a handoff",
             "sequence": ["HOLD_SLOT", "OPEN_DEVIATION"],
             "note": "The handoff is already refused. Adjudication is a separate, human path; "
                     "do not reissue the chain-of-identity reference to clear it."},
        ],
        "external_effect": "This service records the decision. It does not message a site or "
                           "write to a QMS, and will not until a plant connection is signed off.",
    }
