"""Measured safety KPIs.

Section 4.2 of the problem statement sets ten safety KPIs and calls them gates rather than
trends: a red one blocks the capability regardless of efficiency gains. Until now those
numbers lived in a table in a document. A target written in prose is a claim; a target
recomputed from the estate on every build is evidence.

Each KPI is measured twice from the same data - once for the inherited behaviour, once for
the governed path - because a control that reports zero is only meaningful next to the
count it prevented. A KPI whose legacy count is also zero is reported as UNEXERCISED: it
proves nothing about the control, and saying so is more useful than a green tick.

Nothing here can change a gate, a decision or a record. This module only counts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import agents, gates, identity, intelligence, release_gate
from .authority import ActionClass
from .loader import Estate, load
from .reality import reconstruct, site_shortfalls
from .types import Resolution

#: Journeys measured for the patient-level KPIs. Every report states the scope it used.
DEFAULT_SAMPLE = 120

#: Extra journeys pulled in per hazard so that every control is presented with its condition.
SEED_PER_HAZARD = 25

#: Upper bound on a caller-supplied sample. Measuring is read-only but not free.
MAX_SAMPLE = 400

HELD = "HELD"                 # the control was presented with the condition and held
BREACHED = "BREACHED"         # governed count is above target
UNEXERCISED = "UNEXERCISED"   # the measured scope never presented the condition


@dataclass
class KpiResult:
    kpi_id: str
    name: str
    finding: str
    target: int
    legacy: int | None
    governed: int
    exposed: int
    unit: str
    scope: str
    legacy_measure: str
    governed_measure: str
    evidence: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def status(self) -> str:
        """Zero breaches over zero opportunities is not a pass; it is an untested control."""
        if self.governed > self.target:
            return BREACHED
        return HELD if self.exposed else UNEXERCISED

    @property
    def prevented(self) -> int | None:
        if self.legacy is None:
            return None
        return max(self.legacy - self.governed, 0)

    def as_dict(self) -> dict:
        return {"kpi_id": self.kpi_id, "name": self.name, "finding": self.finding,
                "target": self.target, "legacy": self.legacy, "governed": self.governed,
                "exposed": self.exposed, "prevented": self.prevented, "status": self.status,
                "unit": self.unit, "scope": self.scope, "legacy_measure": self.legacy_measure,
                "governed_measure": self.governed_measure, "evidence": self.evidence,
                "note": self.note}


def _sample(est: Estate, size: int) -> list[str]:
    """A stable head slice, deliberately seeded with the journeys that carry each hazard.

    An unseeded head slice measured zero consent-withdrawal breaches over zero
    withdrawn consents and reported it as a pass. The sample is adversarial on purpose:
    a control is only evidenced by the cases that could have defeated it.
    """
    keys = [p["patient_key"] for p in est.patients]
    if size <= 0 or size >= len(keys):
        return keys
    chosen = dict.fromkeys(keys[:size])
    for condition_keys in _hazard_seeds(est).values():
        for k in condition_keys[:SEED_PER_HAZARD]:
            chosen.setdefault(k, None)
    order = {k: i for i, k in enumerate(keys)}
    return sorted(chosen, key=lambda k: order.get(k, len(keys)))


def _hazard_seeds(est: Estate) -> dict[str, list[str]]:
    """Journeys known to present each guarded condition, so no KPI is measured in a vacuum."""
    bad_qc, open_dev = [], []
    for b in est.batches:
        bid, key = b["batch_id"], b["patient_key"]
        if any(r["result"] in {"PENDING", "OOS"} for r in est.qc_by_batch.get(bid, [])):
            bad_qc.append(key)
        if any(d["status"] != "CLOSED" for d in est.deviations_by_batch.get(bid, [])):
            open_dev.append(key)
    return {
        "consent_withdrawn": [c["patient_key"] for c in est.consents
                              if c["status"] == "WITHDRAWN"],
        "unresolved_qc": bad_qc,
        "open_deviation": open_dev,
        "unqualified_centre": [p["patient_key"] for p in est.patients
                               if _unqualified(est, p.get("center_id", ""))],
        "not_released": [b["patient_key"] for b in est.batches
                         if b["qms_release_status"] != "RELEASED"],
    }


def _unqualified(est: Estate, center_id: str) -> bool:
    qual = est.qual_by_center.get(center_id)
    return qual is None or bool(site_shortfalls(qual))


def _gate(assessment, gate_id: str):
    return next(g for g in assessment.gates if g.gate_id == gate_id)


def measure(estate: Estate | None = None, sample: int = DEFAULT_SAMPLE) -> list[KpiResult]:
    est = estate or load()
    keys = _sample(est, sample)
    journey_scope = (f"{len(keys)} of {len(est.patients)} journeys, seeded with every "
                     f"hazard present in the estate")
    assessments = {k: gates.evaluate(k, est) for k in keys}
    decisions = {k: release_gate.evaluate_release(k, est) for k in keys}

    return [
        _readiness_without_release(est, keys, assessments, journey_scope),
        _release_over_unresolved_qc(est, keys, decisions, journey_scope),
        _release_over_open_deviation(est, keys, decisions, journey_scope),
        _progression_at_unqualified_centre(est, keys, assessments, journey_scope),
        _activity_after_consent_withdrawal(est, keys, assessments, journey_scope),
        _identity_merged_without_adjudication(est),
        _disposition_on_untrusted_sensor_data(est),
        _consequential_action_available_to_an_agent(),
    ]


# --------------------------------------------------------------------------- #

def _readiness_without_release(est, keys, assessments, scope) -> KpiResult:
    legacy = release_gate.divergence_report(est)["legacy_says_ready_but_qa_has_not_released"]
    breaches, exposed = [], 0
    for k in keys:
        batches = est.batches_by_key.get(k, [])
        if not batches or any(b["qms_release_status"] == "RELEASED" for b in batches):
            continue
        exposed += 1
        if assessments[k].readiness is gates.Readiness.READY:
            breaches.append(k)
    return KpiResult(
        "SAFE-001", "Readiness asserted without a QA release", "F-ST-001", 0,
        legacy, len(breaches), exposed, "journeys", f"all {len(est.batches)} batches / {scope}",
        "Legacy rule returns ready while the QMS holds no release for the batch.",
        "Governed readiness resolves to READY while the QMS holds no release.",
        breaches[:10])


def _release_over_unresolved_qc(est, keys, decisions, scope) -> KpiResult:
    legacy = release_gate.release_integrity_report(est)["released_with_unresolved_qc"]
    wider = sum(1 for b in est.batches
                if b["qms_release_status"] == "RELEASED"
                and any(r["result"] in {"PENDING", "OOS", "OOT"}
                        for r in est.qc_by_batch.get(b["batch_id"], [])))
    breaches, exposed = [], 0
    for k in keys:
        for b in est.batches_by_key.get(k, []):
            if not any(r["result"] in {"PENDING", "OOS"}
                       for r in est.qc_by_batch.get(b["batch_id"], [])):
                continue
            exposed += 1
            if decisions[k].recommendation != "BLOCK_RELEASE":
                breaches.append(b["batch_id"])
    return KpiResult(
        "SAFE-002", "Release allowed to proceed over unresolved QC", "F-ST-003", 0,
        legacy, len(breaches), exposed, "batches", f"all {len(est.batches)} batches / {scope}",
        "Batch is RELEASED in the QMS while an assay is pending or out of specification.",
        "Governed evaluation does not block while an assay is pending or out of "
        "specification.",
        breaches[:10],
        note=f"The forensic register records {wider} for F-ST-003 because it counts out of "
             f"trend as unresolved. READINESS-2.1 blocks on pending and out of specification "
             f"and reports out of trend as advisory, so the comparable figure is {legacy}. "
             f"The difference is a policy position, not a counting error, and either "
             f"definition may be the right one to adopt.")


def _release_over_open_deviation(est, keys, decisions, scope) -> KpiResult:
    legacy = release_gate.release_integrity_report(est)["released_with_open_deviation"]
    breaches, exposed = [], 0
    for k in keys:
        for b in est.batches_by_key.get(k, []):
            if not any(d["status"] != "CLOSED"
                       for d in est.deviations_by_batch.get(b["batch_id"], [])):
                continue
            exposed += 1
            if decisions[k].recommendation != "BLOCK_RELEASE":
                breaches.append(b["batch_id"])
    return KpiResult(
        "SAFE-003", "Release allowed to proceed over an open deviation", "F-ST-004", 0,
        legacy, len(breaches), exposed, "batches", f"all {len(est.batches)} batches / {scope}",
        "Batch is RELEASED in the QMS while a deviation against it is undispositioned.",
        "Governed evaluation does not block while a deviation against the batch is "
        "undispositioned.",
        breaches[:10])


def _progression_at_unqualified_centre(est, keys, assessments, scope) -> KpiResult:
    legacy = sum(1 for c in est.collections if _unqualified(est, c["center_id"]))
    breaches, exposed = [], 0
    for k in keys:
        centre = est.by_key.get(k, {}).get("center_id", "")
        if not centre or not _unqualified(est, centre):
            continue
        exposed += 1
        if _gate(assessments[k], "G4").status is gates.GateStatus.PASS:
            breaches.append(k)
    return KpiResult(
        "SAFE-004", "Progression allowed at an unqualified centre", "F-GT-006", 0,
        legacy, len(breaches), exposed, "journeys",
        f"all {len(est.collections)} collections / {scope}",
        "A collection was taken at a centre with an open qualification shortfall.",
        "The centre controls gate passes while the qualification record shows a shortfall.",
        breaches[:10])


def _activity_after_consent_withdrawal(est, keys, assessments, scope) -> KpiResult:
    withdrawn = {c["patient_key"] for c in est.consents if c["status"] == "WITHDRAWN"}
    legacy = sum(1 for k in withdrawn
                 if est.collections_by_key.get(k) or est.batches_by_key.get(k)
                 or est.shipments_by_key.get(k))
    seen = [k for k in keys if k in withdrawn]
    breaches = [k for k in seen
                if _gate(assessments[k], "G2").status is gates.GateStatus.PASS]
    return KpiResult(
        "SAFE-005", "Activity after consent withdrawal", "F-GT-002", 0,
        legacy, len(breaches), len(seen), "journeys",
        f"all {len(est.consents)} consents / {scope}",
        "Consent is withdrawn yet a collection, batch or shipment exists for the patient.",
        "The consent gate passes while the consent register records a withdrawal.",
        breaches[:10])


def _identity_merged_without_adjudication(est) -> KpiResult:
    queue = identity.adjudication_queue(est)
    merged = [item["patient_key"] for item in queue
              if identity.propose_merge(item["patient_key"], est).recommendation
              != "DO_NOT_MERGE"]
    return KpiResult(
        "SAFE-006", "Conflicting identity merged without adjudication", "P2", 0,
        len(queue), len(merged), len(queue), "patients", f"all {len(queue)} queued conflicts",
        "Identifiers disagree across sources for this patient.",
        "The merge proposal is anything other than DO_NOT_MERGE while identifiers disagree.",
        merged[:10])


def _disposition_on_untrusted_sensor_data(est) -> KpiResult:
    """The condition is an excursion evidenced only by sensors the sensors themselves distrust.

    A degraded reading below the threshold is not a disposition question, so counting it here
    would inflate both sides and prove nothing.
    """
    exposed, breaches = [], []
    for shipment_id in sorted({t["shipment_id"] for t in est.telemetry}):
        profile = intelligence.excursion_profile(est, shipment_id)
        if not profile["above_threshold"] or profile["sensor_trustworthy"]:
            continue
        exposed.append(shipment_id)
        decision = intelligence.evaluate_excursion(shipment_id, est)
        if decision.action_class is not ActionClass.B_ADVISORY or \
                decision.recommendation != "QA_REVIEW_SENSOR_INTEGRITY":
            breaches.append(shipment_id)
    readings = sum(1 for t in est.telemetry
                   if t["quality"] != "OK" and t["temperature_c"]
                   and float(t["temperature_c"]) > -120.0)
    return KpiResult(
        "SAFE-007", "Disposition taken on untrusted sensor data", "F-LG-002", 0,
        len(exposed), len(breaches), len(exposed), "shipments",
        f"all {len(est.telemetry)} readings",
        "The superseded rule fails product on an above-threshold reading whose sensor was "
        "not flagged OK.",
        "An excursion decision on such a shipment is anything other than an advisory "
        "referral to sensor integrity review.",
        breaches[:10] or exposed[:10],
        note=f"The forensic register counts {readings} such readings; they fall in "
             f"{len(exposed)} shipments, and a shipment is the unit a disposition is taken "
             f"on. The governed count is how many of those shipments the system would still "
             f"disposition on evidence it has no basis to trust.")


def _consequential_action_available_to_an_agent() -> KpiResult:
    consequential = [a.agent_id for a in agents.REGISTRY.values()
                     if a.action_class is ActionClass.D_CONSEQUENTIAL]
    return KpiResult(
        "SAFE-008", "Consequential action available to an autonomous agent", "P1", 0,
        None, len(consequential), len(agents.REGISTRY), "agents",
        f"all {len(agents.REGISTRY)} registered agents",
        "Not measurable: the inherited estate had no authority model to measure against.",
        "An agent in the registry is declared as holding a consequential action.",
        consequential)


# --------------------------------------------------------------------------- #

def report(estate: Estate | None = None, sample: int = DEFAULT_SAMPLE) -> dict:
    results = measure(estate, sample)
    breached = [r for r in results if r.status == BREACHED]
    unexercised = [r for r in results if r.status == UNEXERCISED]
    prevented = sum(r.prevented for r in results if r.prevented is not None)
    return {
        "policy_version": gates.POLICY_VERSION,
        "sample": sample,
        "kpis": [r.as_dict() for r in results],
        "held": len(results) - len(breached) - len(unexercised),
        "breached": len(breached),
        "unexercised": len(unexercised),
        "occurrences_prevented": prevented,
        "safe": not breached,
        "meaning": ("Every safety KPI is at its target on the measured scope."
                    if not breached else
                    f"{len(breached)} safety KPI(s) are above target: "
                    + ", ".join(r.kpi_id for r in breached)),
        "caveat": "These are gates, not trends. They are measured on synthetic data over a "
                  "stated scope. A KPI marked UNEXERCISED is not a pass: the measured scope "
                  "never presented the condition, so the control behind it was not tested.",
    }


# --------------------------------------------------------------------------- #
# Measurement code under change control (govcore.drift)
# --------------------------------------------------------------------------- #

MEASURE_VERSION = "safety-kpi/1.0"

#: A number that proves the system is safe must be as tamper-evident as the rule it measures.
#: Weakening a definition, narrowing the sample or softening the status rule are all ways to
#: turn a red KPI green without touching a gate, so all three are sealed alongside the gates.
SEALED: dict[str, dict] = {
    "SAFE-001": {"statement": "Governed readiness must not resolve to READY while the QMS "
                              "holds no release.",
                 "fn": _readiness_without_release},
    "SAFE-002": {"statement": "Release must not proceed while an assay is pending or out of "
                              "specification.",
                 "fn": _release_over_unresolved_qc},
    "SAFE-003": {"statement": "Release must not proceed while a deviation is undispositioned.",
                 "fn": _release_over_open_deviation},
    "SAFE-004": {"statement": "The centre controls gate must not pass while the qualification "
                              "record shows a shortfall.",
                 "fn": _progression_at_unqualified_centre},
    "SAFE-005": {"statement": "The consent gate must not pass while a withdrawal is on record.",
                 "fn": _activity_after_consent_withdrawal},
    "SAFE-006": {"statement": "A merge must not be proposed while identifiers disagree.",
                 "fn": _identity_merged_without_adjudication},
    "SAFE-007": {"statement": "An excursion evidenced only by untrusted sensors must be "
                              "referred, never dispositioned.",
                 "fn": _disposition_on_untrusted_sensor_data},
    "SAFE-008": {"statement": "No agent may hold a consequential action.",
                 "fn": _consequential_action_available_to_an_agent},
    "KPI-SAMPLE": {"statement": "The measured sample is a stable head slice seeded with every "
                                "hazard present in the estate.",
                   "fn": _sample,
                   "constants": {"DEFAULT_SAMPLE": DEFAULT_SAMPLE,
                                 "SEED_PER_HAZARD": SEED_PER_HAZARD,
                                 "MAX_SAMPLE": MAX_SAMPLE}},
    "KPI-SEEDS": {"statement": "Each guarded condition contributes the journeys that present "
                               "it, so no control is measured in a vacuum.",
                  "fn": _hazard_seeds},
    "KPI-STATUS": {"statement": "Zero breaches over zero opportunities is UNEXERCISED, not a "
                                "pass.",
                   "fn": KpiResult.status.fget},
}


def _main() -> int:
    r = report()
    for k in r["kpis"]:
        mark = {HELD: " ok ", BREACHED: "FAIL", UNEXERCISED: "  ? "}[k["status"]]
        prevented = "n/a" if k["prevented"] is None else str(k["prevented"])
        print(f"[{mark}] {k['kpi_id']}  legacy={str(k['legacy']):>5}  "
              f"governed={k['governed']:<4} exposed={k['exposed']:<5} "
              f"prevented={prevented:<5} {k['name']}")
    if r["unexercised"]:
        print(f"\n{r['unexercised']} KPI(s) were never presented with the condition they "
              f"guard. Widen the sample before reading them as evidence.")
    print(f"\n{r['meaning']}")
    return 0 if r["safe"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
