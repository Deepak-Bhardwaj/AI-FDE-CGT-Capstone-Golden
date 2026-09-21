"""POC-3 - Exception intelligence, degraded mode and the untrusted-content boundary.

Three capabilities that must coexist:
  * decision support that is genuinely useful (ranking, excursion profiling),
  * degraded-mode behaviour that never widens authority,
  * an ingestion boundary where document text can never become an instruction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from . import sop
from .authority import classify
from .loader import Estate, load, parse_time
from .reality import excursion_profile
from .types import ActionClass, Decision, Evidence, Trust, new_decision_id

RULE_VERSION = "intelligence/1.0.0"


# --------------------------------------------------------------------------- #
# Exception ranking (Class B advisory)
# --------------------------------------------------------------------------- #

URGENCY_BY_STATUS = {
    "INFUSION_READY": 100, "RETURN_TRANSIT": 90, "QC_PENDING": 70, "QA_HOLD": 80,
    "IN_MANUFACTURING": 60, "COLLECTED": 50, "APHERESIS_PENDING": 40,
    "ELIGIBLE": 20, "ENROLLED": 10, "INFUSED": 0,
}
SEVERITY_WEIGHT = {"CRITICAL": 40, "MAJOR": 25, "MINOR": 10}


@dataclass
class RankedException:
    exception_id: str
    patient_key: str
    kind: str
    score: float
    drivers: list[str] = field(default_factory=list)
    age_hours: float | None = None
    owner: str | None = None
    authority: str | None = None

    def as_dict(self) -> dict:
        return {
            "exception_id": self.exception_id, "patient_key": self.patient_key,
            "kind": self.kind, "score": round(self.score, 1), "drivers": self.drivers,
            "age_hours": self.age_hours, "owner": self.owner, "authority": self.authority,
        }


def rank_exceptions(estate: Estate | None = None, limit: int = 25,
                    now: datetime | None = None) -> list[RankedException]:
    """Rank by patient impact and time-criticality, not by severity label alone."""
    est = estate or load()
    now = now or datetime.now(timezone.utc)
    ranked: list[RankedException] = []

    for dev in est.deviations:
        if dev["status"] == "CLOSED":
            continue
        patient = est.by_key.get(dev["patient_key"])
        status = patient["journey_status"] if patient else "UNKNOWN"
        urgency = URGENCY_BY_STATUS.get(status, 30)
        severity = SEVERITY_WEIGHT.get(dev["severity"], 10)

        opened = parse_time(dev["opened_at"])
        age = round((now - opened).total_seconds() / 3600, 1) if opened else None
        age_pressure = min((age or 0) / 24.0 * 5, 30)

        drivers = [f"journey={status} (urgency {urgency})", f"severity={dev['severity']}"]
        if age is not None:
            drivers.append(f"open {age}h")

        # A broken audit link raises risk because the deviation cannot be substantiated.
        if dev["linked_event_id"] and dev["linked_event_id"] not in est.event_ids:
            drivers.append("audit trail unresolvable")
            severity += 10

        ranked.append(RankedException(
            dev["deviation_id"], dev["patient_key"], f"DEVIATION:{dev['type']}",
            urgency + severity + age_pressure, drivers, age,
            owner=None, authority="QA_RELEASE_APPROVER"))

    for esc in est.escalations:
        if esc["status"] == "CLOSED":
            continue
        drivers = [f"issue={esc['issue']}"]
        score = 45.0
        if not esc["owner"]:
            drivers.append("no assigned owner")
            score += 20
        ranked.append(RankedException(
            esc["shipment_id"], "", f"ESCALATION:{esc['issue']}", score, drivers,
            owner=esc["owner"] or None, authority="LOGISTICS_LEAD"))

    ranked.sort(key=lambda r: -r.score)
    return ranked[:limit]


# --------------------------------------------------------------------------- #
# Excursion evaluation under SOP-LOG-007 v7 (Class B advisory -> QA disposition)
# --------------------------------------------------------------------------- #

def evaluate_excursion(shipment_id: str, estate: Estate | None = None) -> Decision:
    """Duration- and sensor-quality-aware. Produces a recommendation, never a disposition."""
    est = estate or load()
    bound = sop.bind("SOP-LOG-007 v7")
    profile = excursion_profile(est, shipment_id)
    shipment = next((s for s in est.shipments if s["shipment_id"] == shipment_id), None)
    profile["flagged_by_logistics"] = bool(
        shipment and shipment["temp_excursion"].strip().upper() == "TRUE")

    blocking: list[str] = []
    if profile["above_threshold"] == 0:
        recommendation = "NO_EXCURSION_DETECTED"
        rationale = f"{profile['points']} readings, none above -120C."
    elif not profile["sensor_trustworthy"]:
        recommendation = "QA_REVIEW_SENSOR_INTEGRITY"
        rationale = (f"{profile['above_threshold']} reading(s) above -120C, but none from a sensor "
                     f"flagged OK ({profile['degraded_sensor_points']} degraded points). Under v7 a "
                     "reading from an untrusted sensor is not a basis for disposition.")
        blocking.append("sensor quality not established - product disposition unsafe on this evidence")
    else:
        recommendation = "QA_REVIEW_EXCURSION_PROFILE"
        rationale = (f"{profile['above_threshold_trusted']} trusted reading(s) above -120C over "
                     f"{profile['exposure_window_hours']}h, max {profile['max_temp_c']}C. "
                     "v7 requires duration, cumulative profile and shipper integrity review.")

    if profile["flagged_by_logistics"] and profile["above_threshold"] == 0:
        blocking.append("logistics flagged an excursion that telemetry does not support - reconcile before disposition")

    return Decision(
        decision_id=new_decision_id("excursion", shipment_id),
        decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        subject={"shipment_id": shipment_id},
        action="evaluate_excursion",
        action_class=ActionClass.B_ADVISORY,
        recommendation=recommendation,
        rationale=rationale,
        inputs=[Evidence("TELEMETRY", "excursion.profile", profile, "cryogenic_telemetry.csv")],
        blocking_reasons=blocking,
        sop_id=bound.sop_id,
        sop_version=bound.version,
        rule_version=RULE_VERSION,
        authority_required="QA_RELEASE_APPROVER",
        reversible=True,
    )


def legacy_excursion_failed(temp_c: float | None) -> bool:
    """Verbatim legacy rule (superseded SOP v6). Used only to measure divergence."""
    return False if temp_c is None else temp_c > -120.0


# --------------------------------------------------------------------------- #
# Degraded mode
# --------------------------------------------------------------------------- #

class Health(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


# Actions suspended when a dependency is unavailable. Degradation never widens authority.
SUSPENDED_ON_OUTAGE = {
    "QMS": {"release_product", "disposition_excursion", "evaluate_release_readiness"},
    "LIMS": {"release_product", "evaluate_release_readiness"},
    "TELEMETRY": {"disposition_excursion", "evaluate_excursion"},
    "IDENTITY": {"merge_identity", "correct_coi"},
    "SCHEDULER": {"reserve_slot_provisional", "draft_schedule"},
}


@dataclass
class AuthorityEnvelope:
    health: dict[str, Health]
    suspended: set[str] = field(default_factory=set)
    banners: list[str] = field(default_factory=list)

    def permits(self, action: str) -> bool:
        return action not in self.suspended

    def as_dict(self) -> dict:
        return {"health": {k: v.value for k, v in self.health.items()},
                "suspended_actions": sorted(self.suspended), "banners": self.banners}


def authority_envelope(health: dict[str, Health]) -> AuthorityEnvelope:
    env = AuthorityEnvelope(health=health)
    for system, state in health.items():
        if state is Health.UNAVAILABLE:
            env.suspended |= SUSPENDED_ON_OUTAGE.get(system, set())
            env.banners.append(f"{system} unavailable - dependent decisions suspended, not defaulted")
        elif state is Health.DEGRADED:
            env.banners.append(f"{system} degraded - values shown are last-known and non-authoritative")
    return env


def degraded_release_decision(patient_key: str, health: dict[str, Health],
                              estate: Estate | None = None) -> Decision:
    """EVAL-005. When QMS is unreachable the answer is 'cannot decide', never a fallback."""
    env = authority_envelope(health)
    if not env.permits("evaluate_release_readiness"):
        return Decision(
            decision_id=new_decision_id("degraded-release", patient_key),
            decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            subject={"patient_key": patient_key},
            action="evaluate_release_readiness",
            action_class=ActionClass.B_ADVISORY,
            recommendation="CANNOT_DETERMINE",
            rationale=("Release authority is unavailable. Cached or advisory values (MES, ERP) must not "
                       "substitute for QMS. Escalate to QA via the documented offline procedure."),
            blocking_reasons=env.banners,
            rule_version=RULE_VERSION,
            authority_required="QA_RELEASE_APPROVER",
            outcome="SUSPENDED",
            reversible=True,
        )
    from .release_gate import evaluate_release
    return evaluate_release(patient_key, estate)


# --------------------------------------------------------------------------- #
# Untrusted-content boundary (EVAL-006)
# --------------------------------------------------------------------------- #

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) (rules|instructions)",
    r"disregard (the )?(above|previous|prior)",
    r"you are now",
    r"system\s*:",
    r"mark .{0,30}(released|approved|complete)",
    r"override .{0,20}(approval|quality|qa)",
    r"do not (tell|inform|escalate)",
    r"act as",
    r"new instructions",
]

ALLOWED_PROPOSAL_KINDS = {
    "SLOT_CHANGE_REQUEST", "COI_INTEGRITY_QUERY", "ROUTE_UNCERTAINTY",
    "SITE_READINESS_QUERY", "QA_EXCEPTION_NOTE",
}

SUBJECT_TO_KIND = {
    "slot moved": "SLOT_CHANGE_REQUEST",
    "identity reconciliation": "COI_INTEGRITY_QUERY",
    "courier route": "ROUTE_UNCERTAINTY",
    "site readiness": "SITE_READINESS_QUERY",
    "qa exception": "QA_EXCEPTION_NOTE",
}


@dataclass
class ExtractionResult:
    source_file: str
    trust: Trust
    proposals: list[dict] = field(default_factory=list)
    injection_detected: bool = False
    injection_matches: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)  # must always stay empty

    def as_dict(self) -> dict:
        return {
            "source_file": self.source_file, "trust": self.trust.value,
            "proposals": self.proposals, "injection_detected": self.injection_detected,
            "injection_matches": self.injection_matches, "side_effects": self.side_effects,
        }


def extract_from_document(document: dict) -> ExtractionResult:
    """Parse an untrusted document into schema-constrained proposals.

    The extractor holds no tools and no write capability. Text is scanned for instruction
    patterns and reported as a security signal, but the content is never interpreted as a
    command - a detected injection changes nothing about what the output can do, because
    the output can only ever be a proposal.
    """
    body = document.get("body", "") or ""
    subject = (document.get("subject", "") or "").lower()
    result = ExtractionResult(source_file=document.get("file", "<memory>"), trust=Trust.UNTRUSTED)

    haystack = f"{subject} {body}".lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, haystack):
            result.injection_detected = True
            result.injection_matches.append(pattern)

    kind = next((k for token, k in SUBJECT_TO_KIND.items() if token in subject), None)
    if kind and kind in ALLOWED_PROPOSAL_KINDS:
        patient_key = None
        match = re.search(r"\[(P-\d{5})\]", document.get("subject", "") or "")
        if match:
            patient_key = match.group(1)
        result.proposals.append({
            "kind": kind,
            "patient_key": patient_key,
            "excerpt": body[:200],
            "trust": Trust.UNTRUSTED.value,
            "auto_apply": False,
            "requires": "HUMAN_CONFIRMATION",
            "action_class": ActionClass.B_ADVISORY.value,
        })
    return result


def scan_documents(estate: Estate | None = None) -> dict:
    est = estate or load()
    results = [extract_from_document(mail) for mail in est.emails()]
    return {
        "documents": len(results),
        "proposals": sum(len(r.proposals) for r in results),
        "injections_detected": sum(1 for r in results if r.injection_detected),
        "side_effects": sum(len(r.side_effects) for r in results),
        "auto_applied": 0,
        "results": [r.as_dict() for r in results],
    }


assert classify("disposition_excursion") is ActionClass.D_CONSEQUENTIAL
