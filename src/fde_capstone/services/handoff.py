"""Chain-of-identity verification at a physical handoff.

Autologous material is not interchangeable. At every point where a bag changes hands the
identifiers on the label must be checked against the system of record, by rule, before the
handoff proceeds. A mismatch stops the handoff now - it is not an alert raised later, and it is
not a similarity score. The document is explicit that this step is forbidden to AI, because a
probabilistic match on autologous identity is a patient-safety event rather than a model
quality problem.

Three properties carry the weight:

  - Two independent identifiers are required. One identifier that matches proves only that
    somebody read one label correctly.
  - Every presented identifier must resolve to the same subject. An identifier that resolves to
    a different patient is the wrong-patient case, and it is the reason this module exists.
  - Absence is refusal. An unknown identifier, a missing record, an unreadable label - each
    refuses. Nothing here defaults to proceeding.

The check itself changes nothing. Its verdict is what blocks, and every verdict is recorded
whether it proceeded or not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from . import identity
from .audit import EVIDENCE, HashChain
from .loader import Estate, load
from .reality import reconstruct

CHECK_VERSION = "COI-CHECK-1.0"
LEDGER_PATH = EVIDENCE / "handoff_checks.jsonl"

# At least this many identifiers must be presented and verified. One is not a check.
REQUIRED_IDENTIFIER_COUNT = 2


class HandoffPoint(str, Enum):
    """Every point where the patient's material physically changes hands."""

    COLLECTION_LABELLING = "COLLECTION_LABELLING"
    OUTBOUND_COURIER = "OUTBOUND_COURIER"
    MANUFACTURING_INTAKE = "MANUFACTURING_INTAKE"
    IN_PROCESS_HANDLING = "IN_PROCESS_HANDLING"
    QC_SAMPLING = "QC_SAMPLING"
    LABELLED_RELEASE = "LABELLED_RELEASE"
    RETURN_SHIPMENT = "RETURN_SHIPMENT"


class Outcome(str, Enum):
    PROCEED = "PROCEED"
    REFUSE = "REFUSE"


class HandoffRefused(PermissionError):
    """Raised when a handoff must not proceed."""


# Identifier name -> the field on the record that carries it.
IDENTIFIERS = ("coi_id", "din", "lot_id", "collection_id", "patient_ref")


class UnknownHandoff(KeyError):
    """Raised when the caller names a handoff point that does not exist."""


@dataclass
class Finding:
    identifier: str
    presented: str
    status: str            # MATCH | MISMATCH | UNKNOWN | NOT_ON_RECORD
    resolves_to: str | None
    detail: str

    def as_dict(self) -> dict:
        return {"identifier": self.identifier, "presented": self.presented,
                "status": self.status, "resolves_to": self.resolves_to, "detail": self.detail}


@dataclass
class HandoffDecision:
    check_id: str
    handoff: str
    outcome: Outcome
    subject: str | None
    findings: list[Finding] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    verified_identifiers: list[str] = field(default_factory=list)
    checked_at: str = ""
    checked_by: str = ""
    check_version: str = CHECK_VERSION
    authority: str = "Chain-of-identity control. Deterministic and blocking; never AI."

    @property
    def proceeded(self) -> bool:
        return self.outcome is Outcome.PROCEED

    def as_dict(self) -> dict:
        return {"check_id": self.check_id, "handoff": self.handoff, "outcome": self.outcome.value,
                "subject": self.subject, "findings": [f.as_dict() for f in self.findings],
                "refusals": self.refusals, "verified_identifiers": self.verified_identifiers,
                "checked_at": self.checked_at, "checked_by": self.checked_by,
                "check_version": self.check_version, "authority": self.authority,
                "mechanism": "deterministic rule comparison, no scoring and no inference"}


LEDGER = HashChain(LEDGER_PATH)


def _index(est: Estate) -> dict[str, dict[str, str]]:
    """identifier name -> presented value -> the patient it belongs to."""
    cached = getattr(est, "_coi_index", None)
    if cached is not None:
        return cached

    index: dict[str, dict[str, str]] = {name: {} for name in IDENTIFIERS}
    for collection in est.collections:
        key = collection["patient_key"]
        if collection.get("coi_id"):
            index["coi_id"][collection["coi_id"]] = key
        if collection.get("bag_id"):
            index["din"][collection["bag_id"]] = key
        if collection.get("collection_id"):
            index["collection_id"][collection["collection_id"]] = key
    for batch in est.batches:
        key = batch["patient_key"]
        if batch.get("coi_id"):
            index["coi_id"][batch["coi_id"]] = key
        index["lot_id"][batch["batch_id"]] = key
    for patient_key in est.by_key:
        index["patient_ref"][patient_key] = patient_key

    object.__setattr__(est, "_coi_index", index)
    return index


def _check_id(handoff: str, presented: dict) -> str:
    import hashlib
    raw = f"{handoff}|{sorted(presented.items())}|{datetime.now(timezone.utc).isoformat()}"
    return "COI-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def check(handoff: str, presented: dict[str, str], checked_by: str,
          estate: Estate | None = None) -> HandoffDecision:
    """Compare the identifiers read at the handoff against the record. Refuses by default."""
    est = estate or load()
    try:
        point = HandoffPoint(handoff)
    except ValueError as exc:
        raise UnknownHandoff(handoff) from exc

    index = _index(est)
    cleaned = {name: str(value).strip() for name, value in (presented or {}).items()
               if name in IDENTIFIERS and str(value or "").strip()}

    decision = HandoffDecision(
        check_id=_check_id(point.value, cleaned), handoff=point.value,
        outcome=Outcome.REFUSE, subject=None,
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        checked_by=checked_by)

    unrecognised = sorted(set(presented or {}) - set(IDENTIFIERS))
    if unrecognised:
        decision.refusals.append(
            f"These are not identifiers this control knows how to verify: {', '.join(unrecognised)}.")

    resolved: dict[str, str] = {}
    for name in IDENTIFIERS:
        value = cleaned.get(name)
        if not value:
            continue
        owner = index[name].get(value)
        if owner is None:
            decision.findings.append(Finding(name, value, "UNKNOWN", None,
                                             "No record anywhere carries this identifier."))
            decision.refusals.append(f"{name} '{value}' is not on record.")
            continue
        resolved[name] = owner
        decision.findings.append(Finding(name, value, "MATCH", owner,
                                         f"On record against {owner}."))

    if len(resolved) < REQUIRED_IDENTIFIER_COUNT:
        decision.refusals.append(
            f"A handoff needs {REQUIRED_IDENTIFIER_COUNT} independent identifiers that are on "
            f"record; {len(resolved)} were verified. One identifier proves only that one label "
            "was read correctly.")

    subjects = set(resolved.values())
    if len(subjects) > 1:
        for name, owner in sorted(resolved.items()):
            for finding in decision.findings:
                if finding.identifier == name:
                    finding.status = "MISMATCH"
                    finding.detail = f"Resolves to {owner}, which is not the same subject."
        decision.refusals.append(
            "The identifiers presented belong to different patients: "
            + "; ".join(f"{name}={cleaned[name]} -> {owner}" for name, owner in sorted(resolved.items()))
            + ". This handoff is refused and must not be retried without adjudication.")
        decision.verified_identifiers = sorted(resolved)
        return _record(decision)

    decision.verified_identifiers = sorted(resolved)
    subject = next(iter(subjects), None)
    decision.subject = subject

    if subject:
        assessment = identity.assess(subject, est)
        if assessment.blocking:
            decision.refusals.append(
                f"{subject} has an unresolved identity conflict: "
                f"{'; '.join(assessment.conflicts) or assessment.note}.")

        journey = reconstruct(subject, est)
        if journey.value("consent.status") == "WITHDRAWN":
            decision.refusals.append(
                f"Consent for {subject} is withdrawn. No further handoff of this material may "
                "proceed without clinical authority.")

        expected = _expected(subject, est)
        for name, value in sorted(cleaned.items()):
            known = expected.get(name)
            if known and value not in known:
                for finding in decision.findings:
                    if finding.identifier == name:
                        finding.status = "MISMATCH"
                        finding.detail = (f"{subject} is on record with "
                                          f"{', '.join(sorted(known))}, not this value.")
                decision.refusals.append(
                    f"{name} '{value}' is not the {name} recorded for {subject}.")

    if not decision.refusals:
        decision.outcome = Outcome.PROCEED
    return _record(decision)


def _expected(subject: str, est: Estate) -> dict[str, set[str]]:
    expected: dict[str, set[str]] = {name: set() for name in IDENTIFIERS}
    expected["patient_ref"].add(subject)
    for collection in est.collections_by_key.get(subject, []):
        expected["coi_id"].add(collection.get("coi_id", ""))
        expected["din"].add(collection.get("bag_id", ""))
        expected["collection_id"].add(collection.get("collection_id", ""))
    for batch in est.batches_by_key.get(subject, []):
        expected["coi_id"].add(batch.get("coi_id", ""))
        expected["lot_id"].add(batch["batch_id"])
    return {name: {v for v in values if v} for name, values in expected.items()}


def _record(decision: HandoffDecision) -> HandoffDecision:
    """Every verdict is evidence, whether it proceeded or not."""
    LEDGER.append("handoff_check", decision.as_dict())
    return decision


def assert_may_proceed(handoff: str, presented: dict[str, str], checked_by: str,
                       estate: Estate | None = None) -> HandoffDecision:
    """For callers that intend to act. Raises rather than returning a verdict to ignore."""
    decision = check(handoff, presented, checked_by, estate)
    if not decision.proceeded:
        raise HandoffRefused(
            f"Handoff {decision.handoff} refused. " + " ".join(decision.refusals))
    return decision


def history(subject: str | None = None, limit: int = 50) -> list[dict]:
    rows = LEDGER.recent(limit * 4)
    if subject:
        rows = [r for r in rows if r.get("subject") == subject]
    return rows[:limit]


def points() -> list[dict]:
    return [{"handoff": point.value,
             "description": point.value.replace("_", " ").capitalize()}
            for point in HandoffPoint]
