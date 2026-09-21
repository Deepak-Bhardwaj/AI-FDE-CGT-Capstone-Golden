"""Zero Trust authorization and minimum-necessary field access.

Access requires all of: authenticated identity AND role permits the action AND purpose is
permitted AND journey is in scope AND the requested fields are necessary for the role.

Field redaction is applied on the way out, so a role that should never see a date of birth
cannot see one even if an upstream component includes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .audit import ACCESS_PATH, HashChain


class Purpose(str, Enum):
    CARE_COORDINATION = "CARE_COORDINATION"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    IDENTITY_ADJUDICATION = "IDENTITY_ADJUDICATION"
    LOGISTICS_OPERATIONS = "LOGISTICS_OPERATIONS"
    CAPACITY_PLANNING = "CAPACITY_PLANNING"
    AUDIT = "AUDIT"
    AI_ASSISTANCE = "AI_ASSISTANCE"


class Sensitivity(str, Enum):
    IDENTIFYING = "IDENTIFYING"     # name, dob, mrn
    PSEUDONYMOUS = "PSEUDONYMOUS"   # patient_key, journey ids
    OPERATIONAL = "OPERATIONAL"     # states, timings, sites
    QUALITY = "QUALITY"             # qc, deviations, release
    LOGISTICS = "LOGISTICS"         # shipments, custody, telemetry


FIELD_SENSITIVITY: dict[str, Sensitivity] = {
    "synthetic_name": Sensitivity.IDENTIFYING,
    "patient_name": Sensitivity.IDENTIFYING,
    "full_name": Sensitivity.IDENTIFYING,
    "patient_alias": Sensitivity.IDENTIFYING,
    "dob": Sensitivity.IDENTIFYING,
    "mrn": Sensitivity.IDENTIFYING,
    "identity.dob": Sensitivity.IDENTIFYING,
    "identity.mrn": Sensitivity.IDENTIFYING,
    "crm_patient_id": Sensitivity.PSEUDONYMOUS,
    "clinical_subject_id": Sensitivity.PSEUDONYMOUS,
    "patient_key": Sensitivity.PSEUDONYMOUS,
    "qc.summary": Sensitivity.QUALITY,
    "qc.complete": Sensitivity.QUALITY,
    "deviations.open": Sensitivity.QUALITY,
    "product.released": Sensitivity.QUALITY,
    "custody.excursion_profiles": Sensitivity.LOGISTICS,
    "custody.intact": Sensitivity.LOGISTICS,
}


@dataclass(frozen=True)
class Role:
    name: str
    label: str
    permitted: frozenset[Sensitivity]
    purposes: frozenset[Purpose]
    actions: frozenset[str]
    description: str = ""


ROLES: dict[str, Role] = {
    "ops_coordinator": Role(
        "ops_coordinator", "Operations coordinator",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL}),
        frozenset({Purpose.CARE_COORDINATION}),
        frozenset({"view_journey", "list_exceptions", "rank_exceptions", "open_exception",
                   "record_stage_decision", "register_patient", "check_handoff",
                   "compensate_lot", "acknowledge_alert"}),
        "Determines where a journey is blocked. Never sees identifying fields."),
    "identity_adjudicator": Role(
        "identity_adjudicator", "Identity adjudicator",
        frozenset({Sensitivity.IDENTIFYING, Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL}),
        frozenset({Purpose.IDENTITY_ADJUDICATION}),
        frozenset({"view_journey", "propose_identity_link", "merge_identity", "correct_coi",
                   "record_stage_decision", "adjudicate_registration", "check_handoff",
                   "acknowledge_alert"}),
        "Sees identifying fields, with justification and access audit."),
    "quality_reviewer": Role(
        "quality_reviewer", "Quality reviewer",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL, Sensitivity.QUALITY,
                   Sensitivity.LOGISTICS}),
        frozenset({Purpose.QUALITY_REVIEW}),
        frozenset({"view_journey", "evaluate_release_readiness", "evaluate_excursion",
                   "release_product", "reject_release", "withdraw_rejection",
                   "disposition_excursion", "record_stage_decision",
                   "check_handoff", "compensate_lot", "acknowledge_alert"}),
        "QC, deviations, telemetry and release evidence. Sole release authority."),
    "manufacturing_planner": Role(
        "manufacturing_planner", "Manufacturing planner",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL}),
        frozenset({Purpose.CAPACITY_PLANNING}),
        frozenset({"view_journey", "draft_schedule", "reserve_slot_provisional", "propose_route",
                   "record_stage_decision", "check_handoff", "compensate_lot",
                   "acknowledge_alert"}),
        "Capacity and batch orchestration. Cannot override MES or QMS."),
    "logistics_coordinator": Role(
        "logistics_coordinator", "Logistics coordinator",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL, Sensitivity.LOGISTICS}),
        frozenset({Purpose.LOGISTICS_OPERATIONS}),
        frozenset({"view_journey", "propose_route", "open_exception", "record_stage_decision",
                   "check_handoff", "acknowledge_alert"}),
        "Shipment, custody and material identifiers. Cannot declare material suitable."),
    "auditor": Role(
        "auditor", "Auditor",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL, Sensitivity.QUALITY,
                   Sensitivity.LOGISTICS}),
        frozenset({Purpose.AUDIT}),
        frozenset({"view_journey", "list_exceptions"}),
        "Read-only evidence and decision records."),
    "ai_service": Role(
        "ai_service", "AI service identity",
        frozenset({Sensitivity.PSEUDONYMOUS, Sensitivity.OPERATIONAL}),
        frozenset({Purpose.AI_ASSISTANCE}),
        frozenset({"view_journey", "rank_exceptions", "extract_from_document",
                   "propose_identity_link"}),
        "Specific read tools only. No identifying fields, no consequential action."),
}

REDACTED = "[redacted]"


@dataclass
class AccessDecision:
    allowed: bool
    reason: str
    role: str
    purpose: str
    redacted_fields: list[str] = field(default_factory=list)


@dataclass
class Session:
    identity: str
    role_name: str
    purpose: Purpose
    assigned_journeys: frozenset[str] | None = None  # None = all journeys in scope

    @property
    def role(self) -> Role:
        return ROLES[self.role_name]

    @property
    def kind(self) -> str:
        return "ai" if self.role_name == "ai_service" else "human"


class AccessAudit:
    """Who looked at what, chained so a deleted look is visible as a gap."""

    def __init__(self, path=None) -> None:
        self.chain = HashChain(path or ACCESS_PATH)

    def log(self, session: Session, action: str, subject: str, decision: AccessDecision) -> None:
        self.chain.append("access", {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "identity": session.identity, "role": session.role_name,
            "purpose": session.purpose.value, "action": action, "subject": subject,
            "allowed": decision.allowed, "reason": decision.reason,
            "redacted_fields": decision.redacted_fields,
        })

    @property
    def entries(self) -> list[dict]:
        return self.chain.payloads()

    def recent(self, limit: int = 50) -> list[dict]:
        return self.chain.recent(limit)

    def verify(self) -> dict:
        return self.chain.verify()


AUDIT = AccessAudit()


def authorize(session: Session, action: str, journey_id: str | None = None) -> AccessDecision:
    role = session.role
    if action not in role.actions:
        d = AccessDecision(False, f"role '{role.label}' is not permitted to '{action}'",
                           role.name, session.purpose.value)
    elif session.purpose not in role.purposes:
        d = AccessDecision(False, f"purpose {session.purpose.value} is not permitted for '{role.label}'",
                           role.name, session.purpose.value)
    elif journey_id and session.assigned_journeys is not None and journey_id not in session.assigned_journeys:
        d = AccessDecision(False, f"journey {journey_id} is not in this session's assigned scope",
                           role.name, session.purpose.value)
    else:
        d = AccessDecision(True, "authenticated, role, purpose and scope all satisfied",
                           role.name, session.purpose.value)
    AUDIT.log(session, action, journey_id or "-", d)
    return d


def redact(payload: dict, session: Session) -> tuple[dict, list[str]]:
    """Remove fields the role has no necessity to see. Applied on the way out."""
    permitted = session.role.permitted
    removed: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                full = f"{path}.{key}" if path else key
                sensitivity = FIELD_SENSITIVITY.get(key) or FIELD_SENSITIVITY.get(full)
                if sensitivity and sensitivity not in permitted:
                    removed.append(full)
                    out[key] = REDACTED
                else:
                    out[key] = walk(value, full)
            return out
        if isinstance(node, list):
            return [walk(item, path) for item in node]
        return node

    return walk(payload), removed
