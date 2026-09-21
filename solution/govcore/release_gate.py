"""POC-1 - Governed release readiness.

Closes F-ST-001 (158), F-ST-002 (16), F-ST-003 (283), F-ST-004 (74).

Legacy behaviour:
    product_ready(batch) -> True if MES is MFG_COMPLETE/RELEASED or ERP is AVAILABLE.
Governed behaviour:
    release derives solely from QMS, gated on QC evidence, deviation disposition and a
    QA electronic signature. MES and ERP are displayed as advisory dissent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import gates, sop
from .authority import ACTION_CLASSES, classify
from .loader import Estate, load, phrase
from .reality import Journey, QC_RESULT_WORDS, reconstruct
from .rejection import STORE as REJECTIONS, blocking_reason
from .types import ActionClass, Decision, Evidence, new_decision_id

RULE_VERSION = "release-gate/2.1.0"
RULE_ID = "R-QA-RELEASE"


def evaluate_release(patient_key: str, estate: Estate | None = None,
                     journey: Journey | None = None) -> Decision:
    """Advisory (Class B) readiness evaluation. Never releases anything."""
    est = estate or load()
    j = journey or reconstruct(patient_key, est)
    bound = sop.bind("SOP-QA-014 v4")

    blocking: list[str] = []
    inputs: list[Evidence] = []
    fired: list[str] = []

    def refuse(clause: str, reason: str) -> None:
        blocking.append(reason)
        fired.append(f"{RULE_ID}.{clause}")

    released = j.fact("product.released")
    qc = j.fact("qc.complete")
    qc_summary = j.fact("qc.summary")
    devs = j.fact("deviations.open")
    consent = j.fact("consent.status")
    center = j.fact("center.qualified")

    for f in (released, qc, devs, consent, center):
        if f:
            inputs.extend(f.evidence)

    if released is None:
        refuse("NO_BATCH", "No manufacturing batch exists for this patient yet.")
    else:
        if released.value is not True:
            refuse("NO_QMS_RELEASE",
                   "Quality has not released this batch in the QMS. Completing "
                   "manufacturing is not a release (SOP-QA-014 v4).")
        if released.note:
            # MES/ERP dissent is exactly the legacy false-positive condition.
            refuse("ADVISORY_SYSTEM_DISSENT",
                   f"Advisory systems disagree with the QMS decision: {released.note}")

    if qc is not None and qc.value is not True:
        detail = qc_summary.value if qc_summary else {}
        if detail.get("missing"):
            refuse("ASSAY_NOT_REPORTED",
                   "The laboratory has not reported these required tests: "
                   f"{', '.join(phrase(a) for a in detail['missing'])}.")
        if detail.get("blocking"):
            unresolved = ", ".join(
                f"{phrase(e.split('=')[0])} is {QC_RESULT_WORDS.get(e.split('=')[-1], phrase(e.split('=')[-1]))}"
                for e in detail["blocking"])
            refuse("ASSAY_OUT_OF_SPECIFICATION", f"These test results are unresolved: {unresolved}.")

    if devs is not None and devs.value:
        refuse("DEVIATION_OPEN",
               f"Deviation(s) {', '.join(devs.value)} are still open and have not been "
               "dispositioned by Quality.")

    if consent is not None and consent.value == "WITHDRAWN":
        refuse("CONSENT_WITHDRAWN",
               "The patient has withdrawn consent, so there is no legal basis for release "
               "or any downstream activity.")

    if center is not None and center.value is not True:
        refuse("CENTRE_NOT_QUALIFIED",
               "The collection centre was not fully qualified at the time of collection.")

    for reason in j.blocking_reasons:
        if reason not in blocking:
            refuse("JOURNEY_BLOCKED", reason)

    # A qualified person's recorded decision not to release is a disposition, not a note.
    for rejected in REJECTIONS.standing_for(patient_key):
        refuse("REJECTED_BY_QUALITY", blocking_reason(rejected))

    conflicts = [{"fact": f.name, "assertions": {a.source: a.value for a in f.assertions}}
                 for f in j.conflicts]

    releasable = not blocking
    return Decision(
        decision_id=new_decision_id("release", patient_key),
        decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        subject={"patient_key": patient_key, "batch_id": j.value("batch.id")},
        action="evaluate_release_readiness",
        action_class=ActionClass.B_ADVISORY,
        recommendation="ELIGIBLE_FOR_QA_REVIEW" if releasable else "BLOCK_RELEASE",
        rationale=("Every applicable check has passed. QA may now review the batch and apply an "
                   "electronic signature."
                   if releasable else
                   f"{len(blocking)} check(s) are not satisfied, so release cannot proceed."),
        inputs=inputs,
        conflicts=conflicts,
        blocking_reasons=blocking,
        sop_id=bound.sop_id,
        sop_version=bound.version,
        rule_version=RULE_VERSION,
        rules_fired=fired or [f"{RULE_ID}.ALL_CHECKS_SATISFIED"],
        policy_version=gates.POLICY_VERSION,
        authority_required="QA_RELEASE_APPROVER",
        reversible=True,
    )


def propose_release(patient_key: str, estate: Estate | None = None) -> Decision:
    """Class D proposal. Requires a named QA approver and e-signature to execute."""
    advisory = evaluate_release(patient_key, estate)
    return Decision(
        decision_id=new_decision_id("release-proposal", patient_key),
        decided_at=advisory.decided_at,
        subject=advisory.subject,
        action="release_product",
        action_class=classify("release_product"),
        recommendation=advisory.recommendation,
        rationale=advisory.rationale,
        inputs=advisory.inputs,
        conflicts=advisory.conflicts,
        blocking_reasons=advisory.blocking_reasons,
        sop_id=advisory.sop_id,
        sop_version=advisory.sop_version,
        rule_version=advisory.rule_version,
        rules_fired=advisory.rules_fired,
        policy_version=advisory.policy_version,
        authority_required="QA_RELEASE_APPROVER",
        outcome="PROPOSED",
        reversible=False,
    )


def legacy_product_ready(batch: dict) -> bool:
    """Verbatim copy of the legacy rule, for measuring divergence. Never used for decisions."""
    return batch.get("mes_status") in {"MFG_COMPLETE", "RELEASED"} or batch.get("erp_status") == "AVAILABLE"


def divergence_report(estate: Estate | None = None) -> dict:
    """Quantify where the legacy rule and the governed gate disagree."""
    est = estate or load()
    unsafe_true = safe_agree = governed_blocked = 0
    samples: list[str] = []

    for batch in est.batches:
        legacy = legacy_product_ready(batch)
        governed = batch["qms_release_status"] == "RELEASED"
        if legacy and not governed:
            unsafe_true += 1
            if len(samples) < 10:
                samples.append(batch["batch_id"])
        elif legacy == governed:
            safe_agree += 1
        if not governed:
            governed_blocked += 1

    return {
        "batches": len(est.batches),
        "legacy_says_ready_but_qa_has_not_released": unsafe_true,
        "agreement": safe_agree,
        "governed_not_released": governed_blocked,
        "samples": samples,
    }


def release_integrity_report(estate: Estate | None = None) -> dict:
    """Batches QMS marked RELEASED that should not have been."""
    est = estate or load()
    with_bad_qc, with_open_dev, samples = 0, 0, []

    for batch in est.batches:
        if batch["qms_release_status"] != "RELEASED":
            continue
        bid = batch["batch_id"]
        bad_qc = [r for r in est.qc_by_batch.get(bid, []) if r["result"] in {"PENDING", "OOS"}]
        open_devs = [d for d in est.deviations_by_batch.get(bid, []) if d["status"] != "CLOSED"]
        if bad_qc:
            with_bad_qc += 1
        if open_devs:
            with_open_dev += 1
        if (bad_qc or open_devs) and len(samples) < 10:
            samples.append(bid)

    total_released = sum(1 for b in est.batches if b["qms_release_status"] == "RELEASED")
    return {
        "qms_released": total_released,
        "released_with_unresolved_qc": with_bad_qc,
        "released_with_open_deviation": with_open_dev,
        "samples": samples,
    }


assert ACTION_CLASSES["release_product"] is ActionClass.D_CONSEQUENTIAL
