"""The four conditions that require someone to act now.

The document names them: a new chain-of-identity conflict at or past an irreversible step; a
manufacturing-versus-quality release disagreement inside the return-logistics window; any
attempt to act on withdrawn consent; and the advisory identity presenting a write token.

Each one is written here as a query rather than a description, because a condition nobody can
evaluate is a condition nobody is watching. Each alert says who to wake and what to do, since
an alert that only says something is wrong makes the reader do the diagnosis at three in the
morning.

Two of these look for hazards in the data. The other two look for attempts in the ledgers -
the system already refused them, and the refusal is the thing worth waking someone for.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import identity, security
from .audit import EVIDENCE, HashChain
from .loader import Estate, load

ALERTS_VERSION = "ALERTS-1.1"
STATE_PATH = EVIDENCE / "alert_state.jsonl"

# Once the bag exists, nothing downstream can be undone by cancelling a record.
IRREVERSIBLE_FROM = {"COLLECTED", "IN_MANUFACTURING", "QC_PENDING", "QA_HOLD",
                     "RETURN_TRANSIT", "INFUSION_READY", "INFUSED"}

# MES states that mean the plant has finished. None of them is a quality disposition.
MANUFACTURING_FINISHED = {"RELEASED", "MFG_COMPLETE", "COMPLETE", "COMPLETED"}

# The return leg is the last chance to stop product reaching a treatment centre.
RETURN_IN_FLIGHT = {"BOOKED", "IN_TRANSIT", "DELIVERED"}

CLINICAL_ON_CALL = "Quality and clinical on-call"
PLATFORM_ON_CALL = "Platform on-call and security"


class Severity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"


@dataclass
class Alert:
    code: str
    title: str
    severity: str
    subject: str
    why: str
    action: str
    on_call: str
    evidence: list[str] = field(default_factory=list)
    detected_at: str = ""

    @property
    def alert_id(self) -> str:
        raw = f"{self.code}|{self.subject}|{'|'.join(sorted(self.evidence))}"
        return "ALR-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()

    def as_dict(self) -> dict:
        state = STATE.get(self.alert_id, {})
        acknowledgement = state.get("acknowledged")
        return {"alert_id": self.alert_id, "code": self.code, "title": self.title,
                "severity": self.severity, "subject": self.subject, "why": self.why,
                "action": self.action, "on_call": self.on_call, "evidence": self.evidence,
                "detected_at": self.detected_at,
                "first_seen": state.get("first_seen"),
                "acknowledged": bool(acknowledgement),
                "acknowledgement": acknowledgement}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Durable alert state
#
# An alert_id is derived from its evidence, so acknowledging one acknowledges exactly that
# situation. If the evidence moves, the identifier moves with it and the new situation arrives
# unacknowledged. That is what makes "acknowledged until it changes" mean something.
# --------------------------------------------------------------------------- #

LEDGER = HashChain(STATE_PATH)
STATE: dict[str, dict] = {}


class AlertNotFound(KeyError):
    """Raised when an alert identifier has never been observed."""


def _load_state() -> None:
    STATE.clear()
    for payload in LEDGER.payloads():
        event = payload.get("event")
        if event == "OBSERVED":
            entry = STATE.setdefault(payload["alert_id"],
                                     {"first_seen": None, "acknowledged": None})
            entry["first_seen"] = entry["first_seen"] or payload.get("at")
            continue
        taken = {k: payload.get(k) for k in ("by", "role", "reason", "at", "scope")}
        for alert_id in payload.get("alert_ids") or []:
            entry = STATE.setdefault(alert_id, {"first_seen": None, "acknowledged": None})
            entry["acknowledged"] = taken if event == "ACKNOWLEDGED" else None


_load_state()


def observe(alert: Alert) -> str:
    """Record the first sighting. Later sightings of the same situation are not new."""
    entry = STATE.get(alert.alert_id)
    if entry and entry.get("first_seen"):
        return entry["first_seen"]
    at = alert.detected_at or _now()
    LEDGER.append("alert_state", {"event": "OBSERVED", "alert_id": alert.alert_id,
                                  "code": alert.code, "subject": alert.subject, "at": at})
    STATE.setdefault(alert.alert_id, {"first_seen": None, "acknowledged": None})
    STATE[alert.alert_id]["first_seen"] = at
    return at


def _check_reason(reason: str, what: str) -> str:
    if len((reason or "").strip()) < 10:
        raise ValueError(f"{what} needs a reason of at least 10 characters")
    return reason.strip()


def _known(alert_ids: list[str]) -> list[str]:
    unknown = [a for a in alert_ids if not STATE.get(a, {}).get("first_seen")]
    if unknown:
        raise AlertNotFound(unknown[0])
    return alert_ids


def acknowledge(alert_id: str, by: str, role: str, reason: str) -> dict:
    """Take one alert. It stays on the record; it stops being one nobody has looked at."""
    return _take(_known([alert_id]), by, role, reason, scope="SINGLE")


def acknowledge_many(alert_ids: list[str], by: str, role: str, reason: str,
                     code: str | None = None) -> dict:
    """Take a whole condition in one act.

    Recorded as one event rather than many, because an operator taking a hundred at once is a
    different fact from an operator working through a hundred, and the record should say which.
    """
    outstanding = [a for a in _known(list(dict.fromkeys(alert_ids)))
                   if not STATE.get(a, {}).get("acknowledged")]
    if not outstanding:
        raise ValueError("every alert in that selection has already been taken")
    return _take(outstanding, by, role, reason, scope="GROUP", code=code)


def _take(alert_ids: list[str], by: str, role: str, reason: str, scope: str,
          code: str | None = None) -> dict:
    taken = {"by": by, "role": role, "reason": _check_reason(reason, "acknowledging an alert"),
             "at": _now(), "scope": scope}
    LEDGER.append("alert_state", {"event": "ACKNOWLEDGED", "alert_ids": alert_ids,
                                  "code": code, **taken})
    for alert_id in alert_ids:
        STATE[alert_id]["acknowledged"] = taken
    return {**taken, "alert_ids": alert_ids, "count": len(alert_ids)}


def reopen(alert_id: str, by: str, role: str, reason: str) -> dict:
    """Put an alert back. A bulk acknowledgement taken in error needs a way out."""
    entry = STATE.get(alert_id)
    if entry is None or not entry.get("first_seen"):
        raise AlertNotFound(alert_id)
    if not entry.get("acknowledged"):
        raise ValueError(f"'{alert_id}' is already outstanding")
    record = {"by": by, "role": role,
              "reason": _check_reason(reason, "reopening an alert"), "at": _now()}
    LEDGER.append("alert_state", {"event": "REOPENED", "alert_ids": [alert_id], **record})
    entry["acknowledged"] = None
    return record


def is_new(alert: Alert, since: str | None) -> bool:
    first_seen = STATE.get(alert.alert_id, {}).get("first_seen")
    if first_seen is None:
        return True
    return first_seen > since if since else False


# --------------------------------------------------------------------------- #
# 1. A new COI conflict at or past an irreversible step
# --------------------------------------------------------------------------- #

def coi_conflict_past_irreversible_step(est: Estate) -> list[Alert]:
    out = []
    for patient in est.patients:
        key = patient["patient_key"]
        if patient.get("journey_status") not in IRREVERSIBLE_FROM:
            continue
        assessment = identity.assess(key, est)
        if not assessment.blocking:
            continue
        collections = est.collections_by_key.get(key) or []
        out.append(Alert(
            code="COI_CONFLICT_PAST_IRREVERSIBLE_STEP",
            title="Chain-of-identity conflict on material that has already been collected",
            severity=Severity.CRITICAL,
            subject=key,
            why=f"{key} is at {patient['journey_status']} and the identifiers do not agree: "
                f"{'; '.join(assessment.conflicts) or assessment.note}. The starting material "
                "already exists, so this cannot be resolved by cancelling the record.",
            action="Hold the slot and open a deviation. Refuse every handoff for this material "
                   "until the identity adjudicator has ruled. Do not reissue the "
                   "chain-of-identity reference.",
            on_call=CLINICAL_ON_CALL,
            evidence=[f"identity.assess:{key}"]
                     + [f"collection:{c['collection_id']}" for c in collections[:3]],
            detected_at=_now()))
    return out


# --------------------------------------------------------------------------- #
# 2. MES/QMS release disagreement inside the return-logistics window
# --------------------------------------------------------------------------- #

def release_disagreement_in_return_window(est: Estate) -> list[Alert]:
    out = []
    for batch in est.batches:
        mes, qms = batch.get("mes_status"), batch.get("qms_release_status")
        if mes not in MANUFACTURING_FINISHED or qms == "RELEASED":
            continue
        key = batch["patient_key"]
        returning = [s for s in est.shipments_by_key.get(key, [])
                     if s.get("direction") == "RETURN" and s.get("status") in RETURN_IN_FLIGHT]
        if not returning:
            continue
        shipment = returning[-1]
        delivered = shipment.get("status") == "DELIVERED"
        out.append(Alert(
            code="RELEASE_DISAGREEMENT_IN_RETURN_WINDOW",
            title=("Product has reached the treatment centre without a quality release"
                   if delivered else
                   "Product is moving to the treatment centre without a quality release"),
            severity=Severity.CRITICAL,
            subject=key,
            why=f"Batch {batch['batch_id']} is {mes} in MES but {qms} in the QMS, and return "
                f"shipment {shipment['shipment_id']} is {shipment['status']}. Manufacturing "
                "completion is not a release.",
            action=("The material is already at the centre. Tell them now not to administer it, "
                    "and open a deviation. Quality decides disposition; nobody else."
                    if delivered else
                    "Stop the shipment while it can still be stopped and notify the treatment "
                    "centre not to administer. Quality decides disposition; nobody else."),
            on_call=CLINICAL_ON_CALL,
            evidence=[f"batch:{batch['batch_id']}", f"shipment:{shipment['shipment_id']}",
                      f"status:{shipment['status']}"],
            detected_at=_now()))
    return out


# --------------------------------------------------------------------------- #
# 3. Any attempt to act on withdrawn consent
# --------------------------------------------------------------------------- #

def _withdrawn(est: Estate) -> set[str]:
    return {c["patient_key"] for c in est.consents if c.get("status") == "WITHDRAWN"}


def attempt_on_withdrawn_consent(est: Estate, handoff_checks: list[dict] | None = None,
                                 decisions: list[dict] | None = None) -> list[Alert]:
    """The system already refused these. The attempt is what someone needs to know about."""
    withdrawn = _withdrawn(est)
    out = []

    for check in handoff_checks or []:
        subject = check.get("subject")
        if subject not in withdrawn:
            continue
        out.append(Alert(
            code="ACTION_ON_WITHDRAWN_CONSENT",
            title="A handoff was attempted on material whose consent is withdrawn",
            severity=Severity.CRITICAL,
            subject=subject,
            why=f"{check.get('checked_by', 'someone')} attempted {check.get('handoff')} for "
                f"{subject}, whose consent is withdrawn. The check returned "
                f"{check.get('outcome')}.",
            action="Confirm the material has not moved. Involve the treating clinician before "
                   "any further step, and record the outcome against the patient.",
            on_call=CLINICAL_ON_CALL,
            evidence=[f"handoff_check:{check.get('check_id')}"],
            detected_at=_now()))

    for decision in decisions or []:
        subject = (decision.get("subject") or {}).get("patient_key")
        if subject not in withdrawn:
            continue
        if decision.get("action") in ("view_journey", "check_handoff"):
            continue
        out.append(Alert(
            code="ACTION_ON_WITHDRAWN_CONSENT",
            title="An action was recorded against a patient whose consent is withdrawn",
            severity=Severity.CRITICAL,
            subject=subject,
            why=f"'{decision.get('action')}' was recorded for {subject} by "
                f"{decision.get('approved_by') or 'an unnamed caller'}, whose consent is "
                "withdrawn.",
            action="Establish whether anything irreversible followed. Consent status is a "
                   "clinical question, not an operational one.",
            on_call=CLINICAL_ON_CALL,
            evidence=[f"decision:{decision.get('decision_id')}"],
            detected_at=_now()))
    return out


# --------------------------------------------------------------------------- #
# 4. The advisory identity presenting a write token
# --------------------------------------------------------------------------- #

def sidecar_presenting_a_write_token(access_entries: list[dict] | None = None) -> list[Alert]:
    """The AI identity attempting anything consequential. It should never reach the attempt."""
    from . import authority
    from .types import ActionClass

    out = []
    for entry in access_entries or []:
        if entry.get("role") != "ai_service":
            continue
        action = entry.get("action", "")
        if authority.classify(action) in (ActionClass.A_INFORMATIONAL, ActionClass.B_ADVISORY):
            continue
        out.append(Alert(
            code="SIDECAR_PRESENTED_A_WRITE_TOKEN",
            title="The advisory identity attempted a consequential action",
            severity=Severity.CRITICAL,
            subject=entry.get("identity", "ai_service"),
            why=f"The AI service identity attempted '{action}' on {entry.get('subject', '-')}. "
                f"It was {'refused' if not entry.get('allowed') else 'ALLOWED, which it must never be'}. "
                "The advisory layer holds no write capability by design, so an attempt means "
                "either a defect or a compromise.",
            action="Treat as a security incident. Disable the advisory layer, preserve the "
                   "access chain, and establish what issued the credential.",
            on_call=PLATFORM_ON_CALL,
            evidence=[f"access:{entry.get('at')}:{action}"],
            detected_at=_now()))
    return out


# --------------------------------------------------------------------------- #

@dataclass
class AlertScan:
    alerts: list[Alert] = field(default_factory=list)
    scanned: dict = field(default_factory=dict)

    def outstanding(self) -> list[Alert]:
        return [a for a in self.alerts if not STATE.get(a.alert_id, {}).get("acknowledged")]

    def summary(self) -> dict:
        outstanding = self.outstanding()
        return {"total": len(self.alerts),
                "outstanding": len(outstanding),
                "acknowledged": len(self.alerts) - len(outstanding),
                "by_code": dict(Counter(a.code for a in self.alerts)),
                "by_severity": dict(Counter(a.severity for a in self.alerts)),
                "by_on_call": dict(Counter(a.on_call for a in outstanding))}

    def grouped(self, since: str | None = None, sample: int = 10) -> list[dict]:
        """One page per condition. A hundred instances of one problem is still one problem."""
        by_code: dict[str, list[Alert]] = {}
        for alert in self.alerts:
            by_code.setdefault(alert.code, []).append(alert)

        groups = []
        for condition in CONDITIONS:
            members = by_code.get(condition["code"], [])
            if not members:
                continue
            outstanding = [a for a in members
                           if not STATE.get(a.alert_id, {}).get("acknowledged")]
            new = [a for a in outstanding if is_new(a, since)]
            first = members[0]
            bulk = [a for a in members
                    if (STATE.get(a.alert_id, {}).get("acknowledged") or {}).get("scope") == "GROUP"]
            groups.append({
                "code": condition["code"],
                "condition": condition["condition"],
                "title": first.title,
                "severity": first.severity,
                "on_call": condition["on_call"],
                "action": first.action,
                "total": len(members),
                "outstanding": len(outstanding),
                "acknowledged": len(members) - len(outstanding),
                "acknowledged_in_bulk": len(bulk),
                "new": len(new),
                "subjects": sorted({a.subject for a in outstanding})[:sample],
                "subjects_truncated": len({a.subject for a in outstanding}) > sample,
                "alert_ids": [a.alert_id for a in outstanding[:sample]],
            })
        groups.sort(key=lambda g: (-g["new"], -g["outstanding"]))
        return groups

    def as_dict(self, since: str | None = None) -> dict:
        return {"alerts_version": ALERTS_VERSION,
                "groups": self.grouped(since),
                "alerts": [a.as_dict() for a in self.alerts],
                "summary": self.summary(),
                "scanned": self.scanned,
                "conditions": CONDITIONS,
                "since": since,
                "note": "These four conditions are the ones that require someone to act now. "
                        "Grouped by condition, because a hundred instances of one problem is "
                        "still one problem. Acknowledging an alert records who took it; the "
                        "alert stays on the record."}


CONDITIONS = [
    {"code": "COI_CONFLICT_PAST_IRREVERSIBLE_STEP",
     "condition": "A chain-of-identity conflict on a patient at or past collection",
     "on_call": CLINICAL_ON_CALL},
    {"code": "RELEASE_DISAGREEMENT_IN_RETURN_WINDOW",
     "condition": "MES reports manufacturing finished, the QMS has not released, and the "
                  "return shipment is in flight",
     "on_call": CLINICAL_ON_CALL},
    {"code": "ACTION_ON_WITHDRAWN_CONSENT",
     "condition": "Any attempt to act on a patient whose consent is withdrawn",
     "on_call": CLINICAL_ON_CALL},
    {"code": "SIDECAR_PRESENTED_A_WRITE_TOKEN",
     "condition": "The advisory identity attempting a reversible or consequential action",
     "on_call": PLATFORM_ON_CALL},
]


def scan(estate: Estate | None = None, handoff_checks: list[dict] | None = None,
         decisions: list[dict] | None = None,
         access_entries: list[dict] | None = None) -> AlertScan:
    est = estate or load()
    if access_entries is None:
        access_entries = security.AUDIT.recent(500)

    alerts = (coi_conflict_past_irreversible_step(est)
              + release_disagreement_in_return_window(est)
              + attempt_on_withdrawn_consent(est, handoff_checks, decisions)
              + sidecar_presenting_a_write_token(access_entries))

    seen, unique = set(), []
    for alert in alerts:
        if alert.alert_id in seen:
            continue
        seen.add(alert.alert_id)
        observe(alert)
        unique.append(alert)

    return AlertScan(unique, {"patients": len(est.patients), "batches": len(est.batches),
                              "handoff_checks": len(handoff_checks or []),
                              "decisions": len(decisions or []),
                              "access_entries": len(access_entries)})
