"""POC-2 - Identity resolution and COI adjudication.

Closes F-ID-001 (4 patients on duplicate MRNs) and F-ID-002 (17 CRM/clinical conflicts).

Design rule, from AGENTS.md: never fabricate a linkage when identifiers conflict.
A conflicting DOB or MRN always yields UNRESOLVED and an adjudication item. There is no
score high enough to auto-merge, because one wrong merge is a wrong-patient infusion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..model import Principal, canonical_json, digest_json, utc_now
from ..storage import Database
from .authority import classify
from .cases import CaseService
from .common import authorize, correlation
from .evidence import EvidenceService
from .loader import Estate, load
from .types import ActionClass, Decision, Evidence, new_decision_id

RULE_VERSION = "identity/1.0.0"


class MatchOutcome(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    PROBABLE = "PROBABLE"
    UNRESOLVED = "UNRESOLVED"
    DISTINCT = "DISTINCT"


@dataclass
class IdentityAssessment:
    patient_key: str
    outcome: MatchOutcome
    confidence: float
    agreements: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    blocking: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "patient_key": self.patient_key, "outcome": self.outcome.value,
            "confidence": round(self.confidence, 3), "agreements": self.agreements,
            "conflicts": self.conflicts, "blocking": self.blocking, "note": self.note,
            "evidence": [e.as_dict() for e in self.evidence],
        }


# A conflict on either of these can never be overridden by agreement elsewhere.
SAFETY_CRITICAL_FIELDS = ("dob", "mrn")
FIELD_WEIGHTS = {"mrn": 0.4, "dob": 0.3, "center_id": 0.2, "clinical_subject_id": 0.1}


def assess(patient_key: str, estate: Estate | None = None) -> IdentityAssessment:
    est = estate or load()
    crm = est.crm_by_key.get(patient_key)
    clinical = est.clinical_by_key.get(patient_key)
    patient = est.by_key.get(patient_key)

    if not patient:
        return IdentityAssessment(patient_key, MatchOutcome.UNRESOLVED, 0.0, blocking=True,
                                  note="patient not present in the register")
    if not crm or not clinical:
        return IdentityAssessment(patient_key, MatchOutcome.UNRESOLVED, 0.0, blocking=True,
                                  note="patient absent from one or more source exports")

    agreements, conflicts, evidence, score = [], [], [], 0.0

    for field_name, weight in FIELD_WEIGHTS.items():
        left = crm.get(field_name)
        right = clinical.get(field_name)
        if left is None or right is None:
            continue
        evidence.append(Evidence("CRM", f"identity.{field_name}", left, "crm_patient_export.csv"))
        evidence.append(Evidence("CLINICAL", f"identity.{field_name}", right, "clinical_patient_export.csv"))
        if left == right:
            agreements.append(field_name)
            score += weight
        else:
            conflicts.append(f"{field_name}: CRM={left} CLINICAL={right}")

    # Duplicate MRN across distinct patient_keys is a positive-identification hazard.
    shared = [k for k in est.keys_by_mrn.get(patient["mrn"], []) if k != patient_key]
    if shared:
        conflicts.append(f"mrn {patient['mrn']} also held by {', '.join(shared)}")
        evidence.append(Evidence("IDENTITY_SCAN", "identity.mrn_collision", shared, "patients.csv"))

    safety_conflict = any(c.split(":")[0] in SAFETY_CRITICAL_FIELDS for c in conflicts) or bool(shared)

    if safety_conflict:
        return IdentityAssessment(
            patient_key, MatchOutcome.UNRESOLVED, 0.0, agreements, conflicts, evidence, True,
            "safety-critical identifier conflict - automatic linkage refused, human adjudication required")
    if conflicts:
        return IdentityAssessment(
            patient_key, MatchOutcome.PROBABLE, round(score, 3), agreements, conflicts, evidence, True,
            "non-critical identifier disagreement - propose link, await confirmation")
    if score >= 0.9:
        return IdentityAssessment(
            patient_key, MatchOutcome.DETERMINISTIC, 1.0, agreements, conflicts, evidence, False,
            "all identifiers agree across sources")
    return IdentityAssessment(
        patient_key, MatchOutcome.PROBABLE, round(score, 3), agreements, conflicts, evidence, True,
        "insufficient corroboration for automatic linkage")


def propose_merge(patient_key: str, estate: Estate | None = None) -> Decision:
    """Class D proposal. Cannot execute while blocking conflicts exist."""
    a = assess(patient_key, estate)
    return Decision(
        decision_id=new_decision_id("identity", patient_key),
        decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        subject={"patient_key": patient_key},
        action="merge_identity",
        action_class=classify("merge_identity"),
        recommendation="DO_NOT_MERGE" if a.blocking else "MERGE_CANDIDATE",
        rationale=a.note,
        inputs=a.evidence,
        conflicts=[{"fact": "identity", "assertions": {"detail": a.conflicts}}] if a.conflicts else [],
        blocking_reasons=a.conflicts if a.blocking else [],
        rule_version=RULE_VERSION,
        confidence=a.confidence,
        authority_required="IDENTITY_ADJUDICATOR",
        outcome="PROPOSED",
        reversible=False,
    )


def adjudication_queue(estate: Estate | None = None, limit: int | None = None) -> list[dict]:
    """Everything a human must decide, ranked by clinical urgency."""
    est = estate or load()
    urgency = {"INFUSION_READY": 0, "RETURN_TRANSIT": 1, "QC_PENDING": 2, "IN_MANUFACTURING": 3,
               "QA_HOLD": 4, "COLLECTED": 5, "APHERESIS_PENDING": 6, "ELIGIBLE": 7,
               "ENROLLED": 8, "INFUSED": 9}

    items = []
    for patient in est.patients:
        key = patient["patient_key"]
        a = assess(key, est)
        if not a.blocking:
            continue
        items.append({
            "patient_key": key,
            "outcome": a.outcome.value,
            "journey_status": patient["journey_status"],
            "urgency_rank": urgency.get(patient["journey_status"], 99),
            "conflicts": a.conflicts,
            "note": a.note,
            "action_required": "ADJUDICATE_IDENTITY",
            "authority": "IDENTITY_ADJUDICATOR",
        })

    items.sort(key=lambda i: (i["urgency_rank"], i["patient_key"]))
    return items[:limit] if limit else items


def coi_proposals_from_documents(estate: Estate | None = None) -> list[dict]:
    """COI events that exist only in the email corpus.

    F-ID-004/005/006 all measured zero: structured COI linkage is clean. The real
    chain-of-identity break is in a mailbox, invisible to every structured check.
    Output is a proposal requiring QA confirmation, never an applied correction.
    """
    est = estate or load()
    triggers = ("label replacement", "label swap", "relabel", "verify coi", "identity reconciliation")
    proposals = []

    for mail in est.emails():
        haystack = f"{mail.get('subject','')} {mail.get('body','')}".lower()
        if not any(t in haystack for t in triggers):
            continue
        subject = mail.get("subject", "")
        patient_key = subject[subject.find("[") + 1:subject.find("]")] if "[" in subject else None
        proposals.append({
            "source_file": mail["file"],
            "patient_key": patient_key,
            "trust": "UNTRUSTED",
            "proposed_event": "COI_INTEGRITY_QUERY",
            "proposed_state": "CUSTODY_UNCERTAIN",
            "excerpt": mail.get("body", "")[:180],
            "structured_evidence_present": bool(
                patient_key and est.collections_by_key.get(patient_key)),
            "action_required": "QA_COI_ADJUDICATION",
            "authority": "QA_COI_ADJUDICATOR",
            "auto_apply": False,
        })
    return proposals


class IdentityService:
    """Operational identity cases against the capstone ledger, not the source CSVs."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.cases = CaseService(db)
        self.evidence = EvidenceService(db)

    def detect_conflict(
        self,
        principal: Principal,
        patient_a: str,
        patient_b: str,
        reason: str,
        evidence_refs: list[str],
        correlation_id: str | None = None,
    ) -> dict:
        return self.cases.open_case(
            principal,
            "IDENTITY_CONFLICT",
            f"{patient_a}:{patient_b}",
            "P0",
            principal.subject,
            reason,
            evidence_refs,
            correlation_id,
        )

    def propose(
        self,
        principal: Principal,
        case_id: str,
        patient_a: str,
        patient_b: str,
        relation: str,
        evidence_refs: list[str],
        correlation_id: str | None = None,
    ) -> dict:
        trace = correlation(correlation_id)
        case = self.cases.get(case_id)
        authorize(self.db, principal, "case:create", case["scope"], trace)
        unique_refs = list(dict.fromkeys(evidence_refs))
        if len(unique_refs) < 2:
            raise ValueError("CORROBORATION_REQUIRED")
        if not self.evidence.exists(unique_refs):
            raise ValueError("UNKNOWN_EVIDENCE")
        payload = {
            "case_id": case_id,
            "patient_a": patient_a,
            "patient_b": patient_b,
            "relation": relation,
            "evidence_refs": unique_refs,
        }
        proposal_digest = digest_json(payload)
        existing = self.db.connection.execute(
            "SELECT * FROM identity_proposals WHERE case_id=?",
            (case_id,),
        ).fetchone()
        if existing:
            return {
                "case_id": case_id,
                "patient_a": existing["patient_a"],
                "patient_b": existing["patient_b"],
                "relation": existing["relation"],
                "proposal_digest": existing["proposal_digest"],
                "evidence_refs": json.loads(existing["evidence_refs_json"]),
                "status": existing["status"],
            }
        with self.db._lock, self.db.connection:
            self.db.connection.execute(
                "INSERT INTO identity_proposals VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    case_id,
                    patient_a,
                    patient_b,
                    relation,
                    proposal_digest,
                    canonical_json(unique_refs),
                    "PROPOSED",
                    None,
                    None,
                ),
            )
        self.db.audit(
            principal,
            "case:create",
            case["scope"],
            "ALLOWED",
            {"case_id": case_id, "proposal_digest": proposal_digest},
            trace,
        )
        return {
            "case_id": case_id,
            "patient_a": patient_a,
            "patient_b": patient_b,
            "relation": relation,
            "proposal_digest": proposal_digest,
            "evidence_refs": unique_refs,
            "status": "PROPOSED",
        }

    def decide(
        self,
        principal: Principal,
        case_id: str,
        decision: str,
        proposal_digest: str,
        correlation_id: str | None = None,
    ) -> dict:
        trace = correlation(correlation_id)
        row = self.db.connection.execute(
            "SELECT * FROM identity_proposals WHERE case_id=?",
            (case_id,),
        ).fetchone()
        if not row:
            raise KeyError(case_id)
        scope = f"{row['patient_a']}:{row['patient_b']}"
        authorize(self.db, principal, "identity:decide", scope, trace)
        if row["proposal_digest"] != proposal_digest:
            raise ValueError("PROPOSAL_DIGEST_MISMATCH")
        if row["status"] == "APPLIED" and decision == "APPROVE":
            return {"status": "APPLIED", "replay": True, "case_id": case_id}
        if decision != "APPROVE":
            raise ValueError("UNSUPPORTED_IDENTITY_DECISION")
        now = utc_now()
        with self.db._lock, self.db.connection:
            self.db.connection.execute(
                "INSERT INTO identity_links VALUES(?,?,?,?,?,?,?)",
                (
                    row["patient_a"],
                    row["patient_b"],
                    row["relation"],
                    row["proposal_digest"],
                    principal.subject,
                    row["evidence_refs_json"],
                    now,
                ),
            )
            self.db.connection.execute(
                "UPDATE identity_proposals SET status=?, decided_by=?, applied_at=? WHERE case_id=?",
                ("APPLIED", principal.subject, now, case_id),
            )
        self.db.audit(
            principal,
            "identity:decide",
            scope,
            "ALLOWED",
            {"case_id": case_id, "status": "APPLIED"},
            trace,
        )
        return {"status": "APPLIED", "replay": False, "case_id": case_id}

    def links(self) -> list[dict]:
        return [dict(row) for row in self.db.connection.execute("SELECT * FROM identity_links")]


assert classify("merge_identity") is ActionClass.D_CONSEQUENTIAL
