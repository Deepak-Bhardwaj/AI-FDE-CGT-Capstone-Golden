"""The reconciliation surface.

Six to ten systems each hold a fragment of the same patient, and they disagree. The failure
this guards against is not the disagreement itself - it is collapsing it into one confident
answer. A conflict here always carries both values, both sources and both timestamps, and it
is never resolved automatically. It names the authority who must decide.

Severity is about what a wrong answer would cost, not about how loudly the systems disagree.
A release disagreement can put unreleased product on a courier; a slot disagreement wastes a
plant window. They are not the same hazard and are not ranked the same.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field

from . import pack
from .loader import Estate, load

SURFACE_VERSION = "CONFLICTS-1.0"


class Severity:
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


# What a wrong answer would cost, and who is allowed to decide it.
FIELD_POLICY: dict[str, dict[str, str]] = {
    "release": {
        "severity": Severity.HIGH,
        "authority": "Quality",
        "hazard": "Product could move on a manufacturing signal that is not a quality release.",
    },
    "coi_id": {
        "severity": Severity.HIGH,
        "authority": "QA COI adjudicator",
        "hazard": "More than one chain-of-identity reference is attached to one lot.",
    },
    "identity": {
        "severity": Severity.HIGH,
        "authority": "Identity adjudicator",
        "hazard": "Source systems describe this patient differently.",
    },
    "slot": {
        "severity": Severity.MEDIUM,
        "authority": "Manufacturing planner",
        "hazard": "A plant window may be held or lost on a stale view of the schedule.",
    },
}

DEFAULT_POLICY = {"severity": Severity.MEDIUM, "authority": "Operations",
                  "hazard": "Sources disagree and no owner is assigned to this field."}


def policy_for(field_name: str) -> dict[str, str]:
    return FIELD_POLICY.get(field_name.split(".")[0], DEFAULT_POLICY)


@dataclass
class Conflict:
    conflict_id: str
    lot_id: str | None
    patient_ref: str
    field: str
    left: dict
    right: dict
    note: str
    severity: str
    authority: str
    hazard: str
    resolution: str = "UNRESOLVED"

    def as_dict(self) -> dict:
        return {"conflict_id": self.conflict_id, "lot_id": self.lot_id,
                "patient_ref": self.patient_ref, "field": self.field,
                "left": self.left, "right": self.right, "note": self.note,
                "severity": self.severity, "authority": self.authority, "hazard": self.hazard,
                "resolution": self.resolution,
                "auto_resolvable": False}


def _conflict_id(patient_ref: str, field_name: str, left: dict, right: dict) -> str:
    raw = f"{patient_ref}|{field_name}|{left.get('source')}={left.get('value')}|" \
          f"{right.get('source')}={right.get('value')}"
    return "CFL-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def for_lot(lot_id: str, estate: Estate | None = None) -> list[Conflict]:
    """Every unresolved disagreement attached to one lot."""
    est = estate or load()
    ref = pack.resolve(lot_id, est)
    return _from_ref(ref, est)


def _from_ref(ref: pack.LotRef, est: Estate) -> list[Conflict]:
    out = []
    for raw in pack.conflicts_for(ref, est):
        rule = policy_for(raw["field"])
        out.append(Conflict(
            conflict_id=_conflict_id(ref.patient_key, raw["field"], raw["left"], raw["right"]),
            lot_id=ref.lot_id, patient_ref=ref.patient_key, field=raw["field"],
            left=raw["left"], right=raw["right"], note=raw.get("note", ""),
            severity=rule["severity"], authority=rule["authority"], hazard=rule["hazard"]))
    return out


@dataclass
class ConflictSurface:
    conflicts: list[Conflict] = field(default_factory=list)
    lots_examined: int = 0
    truncated: bool = False
    # Counts describe every conflict that matched, not the page being returned. A surface whose
    # totals shrank when you asked for fewer rows would be a misleading metric.
    matched: list[Conflict] = field(default_factory=list)

    @property
    def lots_affected(self) -> int:
        return len({c.lot_id or c.patient_ref for c in self.matched})

    def summary(self) -> dict:
        return {
            "total": len(self.matched),
            "returned": len(self.conflicts),
            "lots_examined": self.lots_examined,
            "lots_affected": self.lots_affected,
            "by_field": dict(Counter(c.field.split(".")[0] for c in self.matched)),
            "by_severity": dict(Counter(c.severity for c in self.matched)),
            "by_authority": dict(Counter(c.authority for c in self.matched)),
            "release_disagreements": sum(1 for c in self.matched if c.field == "release"),
            "unresolved": sum(1 for c in self.matched if c.resolution == "UNRESOLVED"),
        }

    def as_dict(self) -> dict:
        return {
            "surface_version": SURFACE_VERSION,
            "conflicts": [c.as_dict() for c in self.conflicts],
            "summary": self.summary(),
            "truncated": self.truncated,
            "note": "Both values, both sources and both timestamps are kept. Nothing here is "
                    "resolved automatically; each conflict names the authority who must decide.",
        }


def scan(estate: Estate | None = None, field_name: str | None = None,
         severity: str | None = None, lot_id: str | None = None,
         limit: int = 200) -> ConflictSurface:
    """Population-wide reconciliation. Filters narrow the view; they never resolve anything."""
    est = estate or load()
    surface = ConflictSurface()

    if lot_id:
        refs = [pack.resolve(lot_id, est)]
    else:
        refs = [pack.LotRef(batch["patient_key"], batch) for batch in est.batches]
        seen = {ref.patient_key for ref in refs}
        refs += [pack.LotRef(key, None) for key in est.by_key if key not in seen]

    collected: list[Conflict] = []
    for ref in refs:
        surface.lots_examined += 1
        for conflict in _from_ref(ref, est):
            if field_name and not conflict.field.startswith(field_name):
                continue
            if severity and conflict.severity != severity.upper():
                continue
            collected.append(conflict)

    collected.sort(key=lambda c: (c.severity != Severity.HIGH, c.field, c.patient_ref))
    surface.matched = collected
    surface.truncated = len(collected) > limit
    surface.conflicts = collected[:limit]
    return surface
