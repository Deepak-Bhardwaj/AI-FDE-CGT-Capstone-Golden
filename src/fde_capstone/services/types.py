"""Core value types.

Two ideas carry the whole design:
  1. A fact is never a bare value. It carries evidence, time, authority and dissent.
  2. CONFLICT and UNRESOLVED are legitimate values, not errors.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any


class ActionClass(str, Enum):
    """Authority classes. Class D is never automated."""

    A_INFORMATIONAL = "A"
    B_ADVISORY = "B"
    C_REVERSIBLE = "C"
    D_CONSEQUENTIAL = "D"


class Resolution(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    PROVISIONAL = "PROVISIONAL"
    CONFLICT = "CONFLICT"
    UNRESOLVED = "UNRESOLVED"
    UNKNOWN = "UNKNOWN"


class Trust(str, Enum):
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"


@dataclass(frozen=True)
class Evidence:
    source: str
    fact: str
    value: Any
    ref: str = ""
    valid_time: str | None = None
    transaction_time: str | None = None
    trust: Trust = Trust.TRUSTED

    def as_dict(self) -> dict:
        d = asdict(self)
        d["trust"] = self.trust.value
        return d


@dataclass
class Assertion:
    """One system's claim about one fact."""

    source: str
    value: Any
    authoritative: bool = False
    valid_time: str | None = None
    ref: str = ""


@dataclass
class Fact:
    """A reconciled fact. Dissent is preserved, never discarded."""

    name: str
    value: Any
    resolution: Resolution
    confidence: float = 1.0
    assertions: list[Assertion] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    authority_required: str | None = None
    note: str = ""

    @property
    def is_conflicted(self) -> bool:
        return self.resolution in (Resolution.CONFLICT, Resolution.UNRESOLVED)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "resolution": self.resolution.value,
            "confidence": round(self.confidence, 3),
            "assertions": [asdict(a) for a in self.assertions],
            "evidence": [e.as_dict() for e in self.evidence],
            "authority_required": self.authority_required,
            "note": self.note,
        }


def reconcile(name: str, assertions: list[Assertion], authority_required: str | None = None) -> Fact:
    """Resolve competing assertions without ever inventing agreement."""
    if not assertions:
        return Fact(name, None, Resolution.UNKNOWN, 0.0, [], [], authority_required,
                    "no system asserted this fact")

    ev = [Evidence(a.source, name, a.value, a.ref, a.valid_time) for a in assertions]
    owner = [a for a in assertions if a.authoritative]

    if owner:
        value = owner[0].value
        dissent = [a for a in assertions if not a.authoritative and a.value != value]
        note = ""
        if dissent:
            note = "authoritative owner asserted; dissent preserved: " + ", ".join(
                f"{a.source}={a.value}" for a in dissent)
        return Fact(name, value, Resolution.AUTHORITATIVE, 1.0, assertions, ev, authority_required, note)

    values = {json.dumps(a.value, sort_keys=True, default=str) for a in assertions}
    if len(values) == 1:
        return Fact(name, assertions[0].value, Resolution.PROVISIONAL, 0.6, assertions, ev,
                    authority_required, "no authoritative owner; sources agree")

    return Fact(name, None, Resolution.CONFLICT, 0.0, assertions, ev, authority_required,
                "sources disagree and no authoritative owner asserted; requires adjudication")


@dataclass
class Decision:
    """Immutable record of a decision. Every field exists for audit or TEVV."""

    decision_id: str
    decided_at: str
    subject: dict[str, Any]
    action: str
    action_class: ActionClass
    recommendation: str
    rationale: str
    inputs: list[Evidence] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    sop_id: str | None = None
    sop_version: str | None = None
    rule_version: str | None = None
    rules_fired: list[str] = field(default_factory=list)
    model_name: str | None = None
    model_version: str | None = None
    confidence: float | None = None
    policy_version: str = "2026.3"
    authority_required: str | None = None
    approved_by: str | None = None
    e_signature: str | None = None
    countersigned_by: str | None = None
    countersignature: str | None = None
    approval_id: str | None = None
    outcome: str = "PROPOSED"
    reversible: bool = True

    def as_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "decided_at": self.decided_at,
            "subject": self.subject,
            "action": self.action,
            "action_class": self.action_class.value,
            "recommendation": self.recommendation,
            "rationale": self.rationale,
            "inputs": [e.as_dict() for e in self.inputs],
            "conflicts": self.conflicts,
            "blocking_reasons": self.blocking_reasons,
            "rule": {"sop_id": self.sop_id, "sop_version": self.sop_version,
                     "rule_version": self.rule_version, "rules_fired": self.rules_fired},
            "model": {"name": self.model_name, "version": self.model_version,
                      "confidence": self.confidence},
            "policy_version": self.policy_version,
            "authority_required": self.authority_required,
            "approved_by": self.approved_by,
            "e_signature": self.e_signature,
            "countersigned_by": self.countersigned_by,
            "countersignature": self.countersignature,
            "approval_id": self.approval_id,
            "outcome": self.outcome,
            "reversible": self.reversible,
        }


def new_decision_id(*parts: str) -> str:
    raw = "|".join(parts) + "|" + datetime.now().isoformat(timespec="microseconds")
    return "DEC-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
