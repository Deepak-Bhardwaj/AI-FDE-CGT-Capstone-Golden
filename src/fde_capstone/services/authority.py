"""Authority enforcement.

Class D actions cannot be executed by an automated caller. This is enforced by capability:
execute() requires a human approver identity and an e-signature, and refuses any principal
whose kind is not "human".

Class D also requires a second, different human holding the same authority. One person can
propose a release; no person can complete one alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .types import ActionClass, Decision


class AuthorityError(PermissionError):
    """Raised when an action is attempted without sufficient authority."""


ACTION_CLASSES: dict[str, ActionClass] = {
    # A - informational
    "view_journey": ActionClass.A_INFORMATIONAL,
    "list_exceptions": ActionClass.A_INFORMATIONAL,
    # Observes and reports; it writes nothing. Its verdict is what blocks a handoff.
    "check_handoff": ActionClass.A_INFORMATIONAL,
    # B - advisory
    "rank_exceptions": ActionClass.B_ADVISORY,
    "forecast_release": ActionClass.B_ADVISORY,
    "forecast_journey": ActionClass.B_ADVISORY,
    "explain_readiness": ActionClass.B_ADVISORY,
    "propose_route": ActionClass.B_ADVISORY,
    "propose_identity_link": ActionClass.B_ADVISORY,
    "extract_from_document": ActionClass.B_ADVISORY,
    "evaluate_release_readiness": ActionClass.B_ADVISORY,
    "evaluate_excursion": ActionClass.B_ADVISORY,
    # C - reversible operational
    "draft_schedule": ActionClass.C_REVERSIBLE,
    "reserve_slot_provisional": ActionClass.C_REVERSIBLE,
    "open_exception": ActionClass.C_REVERSIBLE,
    "record_stage_decision": ActionClass.C_REVERSIBLE,
    "register_patient": ActionClass.C_REVERSIBLE,
    "compensate_lot": ActionClass.C_REVERSIBLE,
    "acknowledge_alert": ActionClass.C_REVERSIBLE,
    # Refusing to release is the safe direction and can be withdrawn by its author.
    "reject_release": ActionClass.C_REVERSIBLE,
    "withdraw_rejection": ActionClass.C_REVERSIBLE,
    # D - consequential
    "adjudicate_registration": ActionClass.D_CONSEQUENTIAL,
    "release_product": ActionClass.D_CONSEQUENTIAL,
    "disposition_excursion": ActionClass.D_CONSEQUENTIAL,
    "correct_coi": ActionClass.D_CONSEQUENTIAL,
    "merge_identity": ActionClass.D_CONSEQUENTIAL,
    "set_clinical_priority": ActionClass.D_CONSEQUENTIAL,
    "schedule_conditioning": ActionClass.D_CONSEQUENTIAL,
    "override_consent": ActionClass.D_CONSEQUENTIAL,
}

REQUIRED_ROLE: dict[str, str] = {
    "release_product": "QA_RELEASE_APPROVER",
    "reject_release": "QA_RELEASE_APPROVER",
    "withdraw_rejection": "QA_RELEASE_APPROVER",
    "disposition_excursion": "QA_RELEASE_APPROVER",
    "correct_coi": "QA_COI_ADJUDICATOR",
    "merge_identity": "IDENTITY_ADJUDICATOR",
    "adjudicate_registration": "IDENTITY_ADJUDICATOR",
    "set_clinical_priority": "CLINICAL_AUTHORITY",
    "schedule_conditioning": "CLINICAL_AUTHORITY",
    "override_consent": "CLINICAL_AUTHORITY",
}


@dataclass(frozen=True)
class Principal:
    identity: str
    kind: str  # "human" | "service" | "ai"
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Countersignature:
    """The second half of a two-person approval, produced only by the dual-control store."""

    identity: str
    kind: str
    roles: frozenset[str]
    signature: str
    signed_at: str
    approval_id: str


AI_AGENT = Principal("ai.assistant", "ai", frozenset())
SERVICE = Principal("svc.orchestrator", "service", frozenset())


def classify(action: str) -> ActionClass:
    if action not in ACTION_CLASSES:
        # Unknown actions are treated as consequential. Fail closed.
        return ActionClass.D_CONSEQUENTIAL
    return ACTION_CLASSES[action]


def execute(decision: Decision, principal: Principal, e_signature: str | None = None,
            countersignature: Countersignature | None = None) -> Decision:
    """Apply a decision, enforcing the authority class."""
    cls = classify(decision.action)

    if cls is ActionClass.D_CONSEQUENTIAL:
        if principal.kind != "human":
            raise AuthorityError(
                f"'{decision.action}' is Class D and cannot be executed by a {principal.kind} "
                f"principal ({principal.identity}). Class D requires a named human approver.")
        role = REQUIRED_ROLE.get(decision.action)
        if role and role not in principal.roles:
            raise AuthorityError(
                f"'{decision.action}' requires role {role}; {principal.identity} holds {sorted(principal.roles)}")
        if not e_signature:
            raise AuthorityError(f"'{decision.action}' requires an electronic signature")
        if decision.blocking_reasons:
            raise AuthorityError(
                f"'{decision.action}' has {len(decision.blocking_reasons)} unresolved blocking reason(s); "
                "resolve them before approval")
        if countersignature is None:
            raise AuthorityError(
                f"'{decision.action}' is Class D and requires two distinct approvers; "
                f"{principal.identity} has signed, a second approver must countersign")
        if countersignature.kind != "human":
            raise AuthorityError(
                f"'{decision.action}' cannot be countersigned by a {countersignature.kind} principal")
        if countersignature.identity == principal.identity:
            raise AuthorityError(
                f"'{decision.action}' requires two distinct approvers; {principal.identity} "
                "cannot both sign and countersign")
        if role and role not in countersignature.roles:
            raise AuthorityError(
                f"countersigning '{decision.action}' requires role {role}; "
                f"{countersignature.identity} holds {sorted(countersignature.roles)}")
        if not countersignature.signature:
            raise AuthorityError(
                f"'{decision.action}' requires an electronic signature from the second approver")
        decision.approved_by = principal.identity
        decision.e_signature = e_signature
        decision.countersigned_by = countersignature.identity
        decision.countersignature = countersignature.signature
        decision.approval_id = countersignature.approval_id
        decision.outcome = "EXECUTED"
        decision.reversible = False
    elif cls is ActionClass.C_REVERSIBLE:
        if principal.kind == "ai":
            raise AuthorityError(f"'{decision.action}' is Class C; AI principals propose only")
        decision.approved_by = principal.identity
        decision.outcome = "EXECUTED"
    else:
        decision.outcome = "EXECUTED"

    decision.decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return decision
