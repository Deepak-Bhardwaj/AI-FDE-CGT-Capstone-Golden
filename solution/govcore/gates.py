"""Versioned deterministic readiness gate engine (READINESS-2.1).

Implements the ten gates of the capability stack. Every gate returns one of five
outcomes - missing or contradictory evidence is never reduced to False.

    PASS | FAIL | UNKNOWN | CONFLICT | NOT_APPLICABLE

AI cannot change a gate result. Gate results are computed here and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from . import sop
from .attestations import STORE as ATTESTATIONS
from .loader import Estate, load, parse_time, phrase
from .reality import IDENTITY_LABELS, Journey, QC_RESULT_WORDS, reconstruct, site_shortfalls
from .types import Resolution

POLICY_VERSION = "READINESS-2.1"
REQUIRED_ASSAYS = {"IDENTITY", "POTENCY", "STERILITY", "VIABILITY", "PURITY", "SAFETY"}

# Which rule each gate applies, in one line, with the system whose word decides it. A reviewer
# who can see only the verdict cannot safely disagree with it; a reviewer who can see the rule
# that fired can.
RULES: dict[str, dict] = {
    "G1": {"rule_id": "R-IDENTITY-MATCH", "rule_version": "2.1",
           "statement": "Identifiers must agree across sources, and a medical record number "
                        "must belong to exactly one patient.",
           "source_system": "CRM and clinical exports"},
    "G2": {"rule_id": "R-CONSENT-LIVE", "rule_version": "2.1",
           "statement": "Consent must be present, current and not withdrawn before any "
                        "irreversible step.",
           "source_system": "Consent register"},
    "G3": {"rule_id": "R-PAYER-AUTHORIZATION", "rule_version": "2.1",
           "statement": "Reimbursement authorization must be in force for the planned therapy.",
           "source_system": "Authorizations"},
    "G4": {"rule_id": "R-CENTRE-QUALIFIED", "rule_version": "2.1",
           "statement": "The treatment centre must hold a current qualification for this "
                        "product.",
           "source_system": "Centre qualifications"},
    "G5": {"rule_id": "R-MANUFACTURING-STATE", "rule_version": "2.1",
           "statement": "The batch must have reached a manufacturing state consistent with the "
                        "stage being assessed.",
           "source_system": "MES"},
    "G6": {"rule_id": "R-QC-COMPLETE", "rule_version": "2.1",
           "statement": "Every required assay must be reported and within specification. A "
                        "missing result is not a pass.",
           "source_system": "LIMS"},
    "G7": {"rule_id": "R-DEVIATIONS-CLOSED", "rule_version": "2.1",
           "statement": "No deviation against this batch may remain undispositioned by Quality.",
           "source_system": "QMS"},
    "G8": {"rule_id": "R-QA-RELEASE", "rule_version": "2.1",
           "statement": "Release is a recorded quality disposition in the QMS. Manufacturing "
                        "completion and stock availability are not releases.",
           "source_system": "QMS"},
    "G9": {"rule_id": "R-RETURN-CUSTODY", "rule_version": "2.1",
           "statement": "Return custody must be unbroken and within temperature limits, "
                        "evaluated under the effective logistics SOP.",
           "source_system": "TMS and telemetry"},
    "G10": {"rule_id": "R-CLINICAL-READINESS", "rule_version": "2.1",
            "statement": "The clinical source must confirm the patient is ready for the next "
                         "step.",
            "source_system": "Clinical export"},
}

UNREGISTERED_RULE = {"rule_id": "R-UNREGISTERED", "rule_version": "0",
                     "statement": "This gate has no registered rule, which is itself a defect.",
                     "source_system": "unknown"}


def provenance() -> dict:
    """What decided this, and under which versions."""
    return {"policy_version": POLICY_VERSION,
            "rules": sorted({r["rule_id"] + " v" + r["rule_version"] for r in RULES.values()}),
            "model": {"name": "deterministic-baseline", "version": POLICY_VERSION,
                      "llm_configured": False},
            "mechanism": "Deterministic rule evaluation. No model contributed to any gate."}

# MES batch states in words an operator can read.
MFG_STATE_WORDS = {
    "MFG_COMPLETE": "manufacturing complete",
    "RELEASED": "released",
    "QC_TESTING": "still in quality control testing",
    "QA_HOLD": "on quality assurance hold",
    "INVESTIGATION": "under investigation",
}


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Readiness(str, Enum):
    READY = "READY"                 # every applicable gate passed
    BLOCKED = "BLOCKED"             # at least one gate failed
    CONFLICTED = "CONFLICTED"       # authoritative sources disagree
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"  # no failure, but evidence is missing


@dataclass
class GateResult:
    gate_id: str
    name: str
    status: GateStatus
    reason: str
    authority: str
    evidence_refs: list[str] = field(default_factory=list)
    sop_ref: str | None = None
    advisory: list[str] = field(default_factory=list)
    # Which clause of the rule produced this outcome. Set by the branch that returned.
    clause: str | None = None

    @property
    def rule(self) -> dict:
        return RULES.get(self.gate_id, UNREGISTERED_RULE)

    def as_dict(self) -> dict:
        rule = self.rule
        return {
            "gate_id": self.gate_id, "name": self.name, "status": self.status.value,
            "reason": self.reason, "authority": self.authority,
            "evidence_refs": self.evidence_refs, "sop_ref": self.sop_ref,
            "advisory": self.advisory,
            "rule_id": rule["rule_id"],
            "rule_version": rule["rule_version"],
            "rule_statement": rule["statement"],
            "source_system": rule["source_system"],
            "clause": self.clause,
            "fired": f"{rule['rule_id']}.{self.clause}" if self.clause else rule["rule_id"],
            "policy_version": POLICY_VERSION,
        }


@dataclass
class ReadinessAssessment:
    journey_id: str
    readiness: Readiness
    policy_version: str
    evaluated_at: str
    gates: list[GateResult] = field(default_factory=list)
    required_authority: str = "Quality"
    recommendation: str = ""
    confidence: float = 0.0
    autonomous_action_allowed: bool = False

    def by_status(self, status: GateStatus) -> list[GateResult]:
        return [g for g in self.gates if g.status is status]

    def as_contract(self) -> dict:
        """The copilot response contract from the capability stack."""
        return {
            "journey_id": self.journey_id,
            "readiness": self.readiness.value,
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
            "failed_gates": [g.gate_id for g in self.by_status(GateStatus.FAIL)],
            "unknown_gates": [g.gate_id for g in self.by_status(GateStatus.UNKNOWN)],
            "conflicting_gates": [g.gate_id for g in self.by_status(GateStatus.CONFLICT)],
            "evidence_references": sorted({r for g in self.gates for r in g.evidence_refs}),
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "required_authority": self.required_authority,
            "autonomous_action_allowed": self.autonomous_action_allowed,
            "gates": [g.as_dict() for g in self.gates],
            "rules_fired": [{"gate_id": g.gate_id, "fired": g.as_dict()["fired"],
                             "status": g.status.value, "source_system": g.rule["source_system"]}
                            for g in self.gates],
            "provenance": provenance(),
        }


# --------------------------------------------------------------------------- #
# Individual gates
# --------------------------------------------------------------------------- #

def _gate1_identity(j: Journey, est: Estate) -> GateResult:
    unique = j.fact("identity.mrn_unique")
    dob, mrn = j.fact("identity.dob"), j.fact("identity.mrn")
    coi = j.fact("collection.coi")
    refs = ["patients.csv", "crm_patient_export.csv", "clinical_patient_export.csv"]

    if unique and unique.resolution is Resolution.UNRESOLVED:
        return GateResult("G1", "Identity and COI resolved", GateStatus.CONFLICT,
                          unique.note or "This medical record number is registered to more than "
                                         "one patient.",
                          "Identity adjudicator", refs, clause="MRN_COLLISION")
    for f in (dob, mrn):
        if f and f.is_conflicted:
            field_label = IDENTITY_LABELS[f.name.split(".")[1]]
            return GateResult("G1", "Identity and COI resolved", GateStatus.CONFLICT,
                              f"The {field_label} differs between the source systems. An identity "
                              "adjudicator must decide which record is correct.",
                              "Identity adjudicator", refs,
                              clause=f"SAFETY_CRITICAL_CONFLICT:{f.name.split('.')[1].upper()}")
    if not coi or coi.value is None:
        return GateResult("G1", "Identity and COI resolved", GateStatus.UNKNOWN,
                          "No chain-of-identity record has been created for this patient.",
                          "Identity adjudicator", refs, clause="NO_COI_RECORD")

    advisory = [s for s in j.shadow_signals if "COI" in s or "identity" in s.lower()]
    return GateResult("G1", "Identity and COI resolved", GateStatus.PASS,
                      f"All source systems agree on this patient's identifiers, and chain of "
                      f"identity {coi.value} is established.",
                      "Identity adjudicator", refs + ["collections.csv"], advisory=advisory,
                      clause="ALL_IDENTIFIERS_AGREE")


def _gate2_consent(j: Journey, est: Estate) -> GateResult:
    f = j.fact("consent.status")
    version = j.value("consent.version")
    refs = ["consents.csv"]
    if f is None or f.resolution is Resolution.UNKNOWN:
        return GateResult("G2", "Consent valid and not withdrawn", GateStatus.UNKNOWN,
                          "No consent record was found. A missing record is not the same as "
                          "consent having been given.",
                          "Clinical authority", refs, clause="NO_CONSENT_RECORD")
    if f.value == "WITHDRAWN":
        return GateResult("G2", "Consent valid and not withdrawn", GateStatus.FAIL,
                          "The patient has withdrawn consent, so every downstream step must stop.",
                          "Clinical authority", refs, clause="CONSENT_WITHDRAWN")
    if f.value != "VALID":
        return GateResult("G2", "Consent valid and not withdrawn", GateStatus.FAIL,
                          f"Consent is recorded as {phrase(f.value)}, which is not valid consent.",
                          "Clinical authority", refs)
    advisory = []
    if version and version != "v3":
        advisory.append(f"Consent was signed under version {version}; the current version is v3. "
                        "Confirm the earlier version is still acceptable.")
    return GateResult("G2", "Consent valid and not withdrawn", GateStatus.PASS,
                      f"Consent is valid and signed under version {version}.",
                      "Clinical authority", refs, advisory=advisory)


def _gate3_authorization(j: Journey, est: Estate) -> GateResult:
    f = j.fact("authorization.status")
    refs = ["insurance_authorizations.csv"]
    if f is None or f.resolution is Resolution.UNKNOWN:
        return GateResult("G3", "Authorization approved and valid", GateStatus.UNKNOWN,
                          "No payer authorization record was found for this patient.",
                          "Payer operations", refs)
    if f.value == "APPROVED":
        return GateResult("G3", "Authorization approved and valid", GateStatus.PASS,
                          "The payer has approved funding for this treatment.",
                          "Payer operations", refs)
    if f.value == "DENIED":
        return GateResult("G3", "Authorization approved and valid", GateStatus.FAIL,
                          "The payer has denied funding for this treatment.",
                          "Payer operations", refs)
    return GateResult("G3", "Authorization approved and valid", GateStatus.FAIL,
                      f"Payer authorization is {phrase(f.value)}, not approved. SOP-SCHED-003 v2 "
                      "allows a slot to be held provisionally, but authorization must be confirmed "
                      "again before any clinical milestone.",
                      "Payer operations", refs, sop_ref="SOP-SCHED-003 v2")


def _gate4_site_controls(j: Journey, est: Estate) -> GateResult:
    f = j.fact("center.qualified")
    center_id = est.by_key.get(j.patient_key, {}).get("center_id", "this centre")
    qual = est.qual_by_center.get(center_id)
    refs = ["site_qualifications.csv", "reference/treatment_centers.csv"]
    if f is None or f.resolution is Resolution.UNKNOWN:
        return GateResult("G4", "Treatment centre controls valid", GateStatus.UNKNOWN,
                          f"No qualification record exists for treatment centre {center_id}.",
                          "Quality", refs)
    if f.is_conflicted:
        return GateResult("G4", "Treatment centre controls valid", GateStatus.CONFLICT,
                          f"The reference master data and the operational qualification record "
                          f"disagree about whether {center_id} is qualified. Quality must decide "
                          "which one is correct.",
                          "Quality", refs)
    if f.value is not True:
        shortfalls = site_shortfalls(qual) if qual else []
        detail = (f"Treatment centre {center_id} is not fully qualified: {'; '.join(shortfalls)}."
                  if shortfalls else f"Treatment centre {center_id} is not fully qualified.")
        return GateResult("G4", "Treatment centre controls valid", GateStatus.FAIL,
                          detail, "Quality", refs)
    advisory = [f.note] if f.note else []
    return GateResult("G4", "Treatment centre controls valid", GateStatus.PASS,
                      f"Staff training, equipment qualification and the quality agreement are all "
                      f"current at {center_id}.", "Quality", refs,
                      advisory=advisory)


def _gate5_manufacturing(j: Journey, est: Estate) -> GateResult:
    state = j.value("mfg.state")
    bid = j.value("batch.id")
    if bid is None:
        return GateResult("G5", "Manufacturing completed", GateStatus.NOT_APPLICABLE,
                          "Manufacturing has not started - no batch exists for this patient yet.",
                          "Manufacturing", [])
    refs = [f"batches.csv:{bid}"]
    if state in {"MFG_COMPLETE", "RELEASED"}:
        return GateResult("G5", "Manufacturing completed", GateStatus.PASS,
                          f"Manufacturing has finished - MES reports the batch as "
                          f"{MFG_STATE_WORDS[state]}.", "Manufacturing", refs)
    if state in {"QC_TESTING", "QA_HOLD", "INVESTIGATION"}:
        return GateResult("G5", "Manufacturing completed", GateStatus.FAIL,
                          f"Manufacturing is not finished - MES reports the batch as "
                          f"{MFG_STATE_WORDS[state]}.", "Manufacturing", refs)
    return GateResult("G5", "Manufacturing completed", GateStatus.UNKNOWN,
                      f"MES reports the batch as '{state}', a state that policy {POLICY_VERSION} "
                      "does not recognise. Manufacturing must confirm what it means.",
                      "Manufacturing", refs)


def _assay_phrase(entry: str) -> str:
    """'POTENCY=OOS' -> 'potency is out of specification'."""
    assay, _, result = entry.partition("=")
    return f"{phrase(assay)} is {QC_RESULT_WORDS.get(result, phrase(result))}"


def _gate6_qc(j: Journey, est: Estate) -> GateResult:
    bid = j.value("batch.id")
    if bid is None:
        return GateResult("G6", "Required QC evidence present", GateStatus.NOT_APPLICABLE,
                          "There is no batch to test yet.", "Laboratory", [])
    summary = j.value("qc.summary") or {}
    refs = [f"qc_results.csv:{bid}"]
    missing = summary.get("missing") or []
    blocking = summary.get("blocking") or []
    oot = summary.get("out_of_trend") or []

    if missing:
        return GateResult("G6", "Required QC evidence present", GateStatus.UNKNOWN,
                          "The laboratory has not yet reported these required tests: "
                          f"{', '.join(phrase(a) for a in missing)}.", "Laboratory", refs,
                          clause="ASSAY_NOT_REPORTED")
    if blocking:
        detail = ", ".join(_assay_phrase(entry) for entry in blocking)
        return GateResult("G6", "Required QC evidence present", GateStatus.FAIL,
                          f"These test results are unresolved: {detail}.", "Laboratory", refs,
                          clause="ASSAY_OUT_OF_SPECIFICATION")
    advisory = [f"Out of trend but not blocking: {', '.join(_assay_phrase(e) for e in oot)}."] if oot else []
    return GateResult("G6", "Required QC evidence present", GateStatus.PASS,
                      f"All {len(REQUIRED_ASSAYS)} required tests have been reported and meet "
                      "specification.",
                      "Laboratory", refs, advisory=advisory, clause="ALL_ASSAYS_IN_SPECIFICATION")


def _gate7_deviations(j: Journey, est: Estate) -> GateResult:
    bid = j.value("batch.id")
    if bid is None:
        return GateResult("G7", "Deviations resolved or dispositioned", GateStatus.NOT_APPLICABLE,
                          "There is no batch, so there are no deviations to review.", "Quality", [])
    open_devs = j.value("deviations.open") or []
    refs = [f"deviations.csv:{bid}"]
    advisory = [u for u in j.uncertainties if u.startswith("Audit trail:")]
    if open_devs:
        return GateResult("G7", "Deviations resolved or dispositioned", GateStatus.FAIL,
                          f"Deviation(s) {', '.join(open_devs)} are still open and have not been "
                          "dispositioned by Quality.",
                          "Quality", refs, advisory=advisory)
    return GateResult("G7", "Deviations resolved or dispositioned", GateStatus.PASS,
                      "There are no open deviations against this batch.",
                      "Quality", refs, advisory=advisory)


def _gate8_qms_release(j: Journey, est: Estate) -> GateResult:
    f = j.fact("product.released")
    bid = j.value("batch.id")
    if f is None:
        return GateResult("G8", "QMS release explicitly approved", GateStatus.NOT_APPLICABLE,
                          "There is no batch, so there is nothing to release.", "Quality", [])
    bound = sop.bind("SOP-QA-014 v4")
    refs = [f"batches.csv:{bid}"]
    advisory = [f.note] if f.note else []
    if f.value is True:
        return GateResult("G8", "QMS release explicitly approved", GateStatus.PASS,
                          "Quality has recorded an explicit release of this batch in the QMS.",
                          "Quality", refs, sop_ref=bound.ref, advisory=advisory,
                          clause="QMS_RELEASE_RECORDED")
    return GateResult("G8", "QMS release explicitly approved", GateStatus.FAIL,
                      "Quality has not released this batch in the QMS. Stock being available in ERP "
                      "or manufacturing being complete in MES does not count as a release "
                      "(SOP-QA-014 v4).", "Quality", refs, sop_ref=bound.ref, advisory=advisory,
                      clause="NO_QMS_RELEASE")


def _gate9_return_custody(j: Journey, est: Estate) -> GateResult:
    key = j.patient_key
    returns = [s for s in est.shipments_by_key.get(key, []) if s["direction"] == "RETURN"]
    if not returns:
        return GateResult("G9", "Return shipment delivered with acceptable custody",
                          GateStatus.NOT_APPLICABLE,
                          "The return shipment to the treatment centre has not been raised yet.",
                          "Logistics", [])
    ship = returns[0]
    refs = [f"shipments.csv:{ship['shipment_id']}"]
    dep, arr = parse_time(ship["departed_at"]), parse_time(ship["arrived_at"])

    if dep and arr and arr < dep:
        return GateResult("G9", "Return shipment delivered with acceptable custody", GateStatus.CONFLICT,
                          f"Shipment {ship['shipment_id']} records an arrival earlier than its "
                          "departure, so the custody timeline cannot be trusted.", "Logistics", refs)
    if not ship["arrived_at"]:
        return GateResult("G9", "Return shipment delivered with acceptable custody", GateStatus.UNKNOWN,
                          f"Shipment {ship['shipment_id']} has no recorded arrival, so delivery "
                          "cannot be confirmed.", "Logistics", refs)
    if ship["status"] != "DELIVERED":
        return GateResult("G9", "Return shipment delivered with acceptable custody", GateStatus.FAIL,
                          f"Shipment {ship['shipment_id']} is {phrase(ship['status'])} rather than "
                          "delivered.", "Logistics", refs)

    profiles = j.value("custody.excursion_profiles") or []
    profile = next((p for p in profiles if p["shipment_id"] == ship["shipment_id"]), None)
    if profile and profile["above_threshold"]:
        bound = sop.bind("SOP-LOG-007 v7")
        trusted = profile["above_threshold_trusted"]
        return GateResult("G9", "Return shipment delivered with acceptable custody", GateStatus.CONFLICT,
                          f"The shipment recorded {profile['above_threshold']} temperature "
                          f"reading(s) warmer than -120C, {trusted} of them from a sensor reporting "
                          "good data quality. Quality must assess the excursion before release "
                          "(SOP-LOG-007 v7).",
                          "Quality", refs + ["cryogenic_telemetry.csv"], sop_ref=bound.ref)
    advisory = [u for u in j.uncertainties if "service level" in u]
    return GateResult("G9", "Return shipment delivered with acceptable custody", GateStatus.PASS,
                      "Delivered with custody intact and no temperature excursion in the telemetry.",
                      "Logistics", refs, advisory=advisory)


def _gate10_clinical(j: Journey, est: Estate) -> GateResult:
    """No system in this estate asserts clinical prerequisites.

    Reporting PASS here would fabricate evidence. UNKNOWN is the honest answer and it
    forces a named clinical confirmation before any journey can be declared READY.
    """
    return GateResult("G10", "Clinical prerequisites confirmed by authoritative source",
                      GateStatus.UNKNOWN,
                      "No system in this estate records whether conditioning and infusion "
                      "prerequisites are met. The treatment centre must confirm them explicitly.",
                      "Treatment centre clinician", [])


GATES = (_gate1_identity, _gate2_consent, _gate3_authorization, _gate4_site_controls,
         _gate5_manufacturing, _gate6_qc, _gate7_deviations, _gate8_qms_release,
         _gate9_return_custody, _gate10_clinical)

OPEN = (GateStatus.FAIL, GateStatus.CONFLICT, GateStatus.UNKNOWN)

# Gates a signed statement can never clear. QA release is satisfied by a QMS signal plus a
# two-person disposition, so one person's word that a release happened is not the release.
NON_ATTESTABLE: dict[str, str] = {
    "G8": "QA release is satisfied only by a release recorded in the QMS together with a "
          "two-person disposition. A signed statement that a release happened is not the "
          "release, and one signature is not dual control.",
}


def _attestation_refused(result: GateResult, att) -> GateResult:
    """The statement is kept and shown. It simply does not move this gate."""
    return GateResult(
        result.gate_id, result.name, result.status, result.reason, result.authority,
        result.evidence_refs + [f"attestation:{att.attestation_id}"],
        result.sop_ref,
        result.advisory + [
            f"{att.by} ({att.authority}) attested on {att.attested_at[:10]}: "
            f"{att.justification} This gate does not clear on an attestation. "
            f"{NON_ATTESTABLE[result.gate_id]}"],
        clause=result.clause,
    )


def _apply_attestation(result: GateResult, att) -> GateResult:
    """A signed statement by the owning authority clears a gate, and says so on its face."""
    if result.gate_id in NON_ATTESTABLE:
        return _attestation_refused(result, att)
    return GateResult(
        result.gate_id, result.name, GateStatus.PASS,
        f"Cleared on a signed attestation by {att.by} ({att.authority}) on "
        f"{att.attested_at[:10]}: {att.justification}",
        result.authority,
        result.evidence_refs + [f"attestation:{att.attestation_id}"],
        result.sop_ref,
        result.advisory + [
            f"Attested, not evidenced. The source systems still report: {result.reason} "
            f"This gate reverts if the attestation is withdrawn or contradicted at the next read."],
        clause=f"CLEARED_ON_ATTESTATION:{result.clause or result.status.value}",
    )


# --------------------------------------------------------------------------- #

def evaluate(patient_key: str, estate: Estate | None = None,
             journey: Journey | None = None) -> ReadinessAssessment:
    est = estate or load()
    j = journey or reconstruct(patient_key, est)
    results = [gate(j, est) for gate in GATES]

    attested = ATTESTATIONS.live_by_gate(patient_key)
    results = [_apply_attestation(g, attested[g.gate_id])
               if g.status in OPEN and g.gate_id in attested else g
               for g in results]

    failed = [g for g in results if g.status is GateStatus.FAIL]
    conflicted = [g for g in results if g.status is GateStatus.CONFLICT]
    unknown = [g for g in results if g.status is GateStatus.UNKNOWN]

    if conflicted:
        readiness = Readiness.CONFLICTED
        recommendation = (f"{len(conflicted)} check(s) have sources that contradict each other. "
                          f"{conflicted[0].authority} must adjudicate them before this journey is "
                          "assessed further - contradictory evidence must never be settled by "
                          "preferring one system.")
        authority = conflicted[0].authority
    elif failed:
        readiness = Readiness.BLOCKED
        recommendation = (f"{len(failed)} check(s) have failed. {failed[0].authority} must resolve "
                          "them before this journey can progress.")
        authority = failed[0].authority
    elif unknown:
        readiness = Readiness.NEEDS_EVIDENCE
        recommendation = (f"{len(unknown)} check(s) have no evidence either way. "
                          f"{unknown[0].authority} must supply it - missing evidence is not a pass.")
        authority = unknown[0].authority
    else:
        readiness = Readiness.READY
        recommendation = ("Every applicable check has passed. An authorized reviewer may now "
                          "proceed with the next step.")
        authority = "Quality"

    applicable = [g for g in results if g.status is not GateStatus.NOT_APPLICABLE]
    confidence = round(sum(1 for g in applicable if g.status is GateStatus.PASS) / len(applicable), 3) \
        if applicable else 0.0

    return ReadinessAssessment(
        journey_id=patient_key,
        readiness=readiness,
        policy_version=POLICY_VERSION,
        evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        gates=results,
        required_authority=authority,
        recommendation=recommendation,
        confidence=confidence,
        autonomous_action_allowed=False,  # invariant: never true
    )


def population_summary(estate: Estate | None = None, limit: int | None = None) -> dict:
    est = estate or load()
    keys = [p["patient_key"] for p in est.patients][:limit] if limit else \
        [p["patient_key"] for p in est.patients]
    counts: dict[str, int] = {r.value: 0 for r in Readiness}
    gate_fail: dict[str, int] = {}

    for key in keys:
        a = evaluate(key, est)
        counts[a.readiness.value] += 1
        for g in a.gates:
            if g.status in (GateStatus.FAIL, GateStatus.CONFLICT):
                gate_fail[g.gate_id] = gate_fail.get(g.gate_id, 0) + 1

    return {"evaluated": len(keys), "readiness": counts,
            "gate_failures": dict(sorted(gate_fail.items()))}
