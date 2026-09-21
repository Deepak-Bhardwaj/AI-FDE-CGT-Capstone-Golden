"""Reconstruct operational reality from conflicting evidence.

Assembles one governed view of a patient journey from nine source systems plus the
shadow channel. Where systems disagree, the disagreement is materialised as a CONFLICT
fact with every assertion preserved. Nothing is averaged, merged or guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .loader import Estate, load, parse_time, phrase
from .types import Assertion, Evidence, Fact, Resolution, Trust, reconcile

REQUIRED_ASSAYS = {"IDENTITY", "POTENCY", "STERILITY", "VIABILITY", "PURITY", "SAFETY"}
BLOCKING_QC = {"PENDING", "OOS"}
EXCURSION_THRESHOLD_C = -120.0

# Operator-facing names for the reconciled identity fields.
IDENTITY_LABELS = {"dob": "date of birth", "mrn": "medical record number",
                   "center_id": "treatment centre"}

# LIMS result codes in words.
QC_RESULT_WORDS = {"PENDING": "still pending", "OOS": "out of specification",
                   "OOT": "out of trend", "PASS": "within specification"}


@dataclass
class Journey:
    patient_key: str
    facts: dict[str, Fact] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    shadow_signals: list[str] = field(default_factory=list)
    state: str = "UNKNOWN"

    @property
    def conflicts(self) -> list[Fact]:
        return [f for f in self.facts.values() if f.is_conflicted]

    def fact(self, name: str) -> Fact | None:
        return self.facts.get(name)

    def value(self, name: str, default=None):
        f = self.facts.get(name)
        return default if f is None else f.value

    def evidence(self) -> list[Evidence]:
        out: list[Evidence] = []
        for f in self.facts.values():
            out.extend(f.evidence)
        return out

    def as_dict(self) -> dict:
        return {
            "patient_key": self.patient_key,
            "state": self.state,
            "facts": {k: v.as_dict() for k, v in self.facts.items()},
            "conflicts": [f.name for f in self.conflicts],
            "blocking_reasons": self.blocking_reasons,
            "uncertainties": self.uncertainties,
            "shadow_signals": self.shadow_signals,
        }


def excursion_profile(estate: Estate, shipment_id: str) -> dict:
    """Duration and sensor-quality aware profile, per SOP-LOG-007 v7.

    v6 asked only 'is any point above threshold'. v7 needs the shape of the exposure
    and whether the sensor reporting it can be trusted at all.
    """
    points = sorted(estate.telemetry_by_shipment.get(shipment_id, []),
                    key=lambda t: t["timestamp"])
    above = [p for p in points if p["temperature_c"] and float(p["temperature_c"]) > EXCURSION_THRESHOLD_C]
    trusted_above = [p for p in above if p["quality"] == "OK"]
    degraded = [p for p in points if p["quality"] != "OK"]

    window = timedelta()
    if len(above) > 1:
        first, last = parse_time(above[0]["timestamp"]), parse_time(above[-1]["timestamp"])
        if first and last:
            window = last - first

    return {
        "shipment_id": shipment_id,
        "points": len(points),
        "above_threshold": len(above),
        "above_threshold_trusted": len(trusted_above),
        "degraded_sensor_points": len(degraded),
        "max_temp_c": max((float(p["temperature_c"]) for p in above), default=None),
        "exposure_window_hours": round(window.total_seconds() / 3600, 2),
        "sensor_trustworthy": len(above) == 0 or len(trusted_above) > 0,
    }


def site_shortfalls(qual: dict) -> list[str]:
    """Why a treatment centre is not fully qualified, in words an operator can act on."""
    problems = []
    if qual["training_status"] == "EXPIRED":
        problems.append("staff training has expired")
    if qual["equipment_status"] == "DUE":
        problems.append("equipment qualification is overdue")
    if qual["quality_agreement"] != "SIGNED":
        problems.append(f"the quality agreement is {phrase(qual['quality_agreement'])}")
    return problems


def reconstruct(patient_key: str, estate: Estate | None = None) -> Journey:
    est = estate or load()
    j = Journey(patient_key)

    patient = est.by_key.get(patient_key)
    if not patient:
        j.state = "NOT_FOUND"
        j.blocking_reasons.append(f"Patient {patient_key} does not exist in the patient register.")
        return j

    crm = est.crm_by_key.get(patient_key)
    clinical = est.clinical_by_key.get(patient_key)

    # ---- identity -------------------------------------------------------------
    # No master identity service exists, so no source is authoritative. Disagreement
    # must surface as CONFLICT rather than be resolved by read order.
    for field_name, crm_field, clin_field in (("dob", "dob", "dob"),
                                              ("mrn", "mrn", "mrn"),
                                              ("center_id", "center_id", "center_id")):
        assertions = []
        if crm:
            assertions.append(Assertion("CRM", crm[crm_field], False, crm.get("enrolled_at"), "crm_patient_export.csv"))
        if clinical:
            assertions.append(Assertion("CLINICAL", clinical[clin_field], False, None, "clinical_patient_export.csv"))
        j.facts[f"identity.{field_name}"] = reconcile(f"identity.{field_name}", assertions,
                                                      authority_required="IDENTITY_ADJUDICATOR")

    shared = [k for k in est.keys_by_mrn.get(patient["mrn"], []) if k != patient_key]
    j.facts["identity.mrn_unique"] = Fact(
        "identity.mrn_unique", not shared,
        Resolution.AUTHORITATIVE if not shared else Resolution.UNRESOLVED,
        1.0 if not shared else 0.0,
        [Assertion("IDENTITY_SCAN", not shared, True, None, "patients.csv")],
        [Evidence("IDENTITY_SCAN", "identity.mrn_unique", not shared, "patients.csv")],
        "IDENTITY_ADJUDICATOR",
        "" if not shared else (f"Medical record number {patient['mrn']} is also registered to "
                               f"{', '.join(shared)}."))

    if shared:
        j.blocking_reasons.append(
            f"Identity: medical record number {patient['mrn']} is shared with {', '.join(shared)}, "
            "so this patient cannot be positively identified.")
    for name in ("identity.dob", "identity.mrn"):
        if j.facts[name].is_conflicted:
            field_label = IDENTITY_LABELS[name.split(".")[1]]
            j.blocking_reasons.append(
                f"Identity: the {field_label} in the CRM does not match the clinical system. "
                "An identity adjudicator must decide which record is correct - the two records "
                "must never be merged automatically.")

    # ---- consent --------------------------------------------------------------
    consent = est.consent_by_key.get(patient_key)
    if consent:
        j.facts["consent.status"] = reconcile(
            "consent.status",
            [Assertion("CONSENT", consent["status"], True, consent.get("signed_at"), consent["consent_id"])],
            "CLINICAL_AUTHORITY")
        j.facts["consent.version"] = reconcile(
            "consent.version",
            [Assertion("CONSENT", consent["version"], True, consent.get("signed_at"), consent["consent_id"])])
        if consent["status"] == "WITHDRAWN":
            j.blocking_reasons.append(
                "Consent: the patient has withdrawn consent. No downstream activity may continue, "
                "and none of it may be automated.")
    else:
        j.facts["consent.status"] = reconcile("consent.status", [], "CLINICAL_AUTHORITY")
        j.blocking_reasons.append("Consent: no consent record was found for this patient.")

    # ---- payer authorization --------------------------------------------------
    auth = est.auth_by_key.get(patient_key)
    if auth:
        j.facts["authorization.status"] = reconcile(
            "authorization.status",
            [Assertion("PAYER", auth["status"], True, auth.get("updated_at"), auth["auth_id"])])

    # ---- treatment centre qualification --------------------------------------
    center_id = patient["center_id"]
    qual = est.qual_by_center.get(center_id)
    ref_center = est.center_by_id.get(center_id)
    if qual:
        compliant = (qual["training_status"] != "EXPIRED"
                     and qual["equipment_status"] != "DUE"
                     and qual["quality_agreement"] == "SIGNED")
        assertions = [Assertion("QMS_SITE", compliant, True, None, f"site_qualifications:{center_id}")]
        if ref_center:
            assertions.append(Assertion("REFERENCE_MDM", ref_center["qualification_status"] == "QUALIFIED",
                                        False, None, f"treatment_centers:{center_id}"))
        j.facts["center.qualified"] = reconcile("center.qualified", assertions, "QA_RELEASE_APPROVER")
        if not compliant:
            j.blocking_reasons.append(
                f"Treatment centre {center_id} is not fully qualified: "
                f"{'; '.join(site_shortfalls(qual))}.")

    # ---- collection -----------------------------------------------------------
    collections = est.collections_by_key.get(patient_key, [])
    if collections:
        col = collections[0]
        j.facts["collection.quality"] = reconcile(
            "collection.quality",
            [Assertion("CENTER", col["quality_flag"], True, col.get("collection_time"), col["collection_id"])])
        j.facts["collection.coi"] = reconcile(
            "collection.coi",
            [Assertion("COI_REGISTER", col["coi_id"], True, col.get("collection_time"), col["collection_id"])])
        if col["quality_flag"] != "ACCEPTABLE":
            j.uncertainties.append(
                f"Collection {col['collection_id']} was flagged {phrase(col['quality_flag'])} with "
                f"{col['viability_pct']}% cell viability, which is a risk to manufacturing downstream.")

    # ---- custody and cryogenic exposure --------------------------------------
    shipments = est.shipments_by_key.get(patient_key, [])
    profiles, custody_ok = [], True
    for ship in shipments:
        dep, arr = parse_time(ship["departed_at"]), parse_time(ship["arrived_at"])
        if dep and arr and arr < dep:
            custody_ok = False
            j.uncertainties.append(
                f"Shipment {ship['shipment_id']} is recorded as having arrived before it departed. "
                "The timeline cannot be trusted and has deliberately not been corrected.")
        if not ship["arrived_at"]:
            custody_ok = False
            j.uncertainties.append(
                f"Shipment {ship['shipment_id']} has no recorded arrival time, so delivery cannot "
                "be confirmed.")
        profile = excursion_profile(est, ship["shipment_id"])
        profile["flagged_by_logistics"] = ship["temp_excursion"].strip().upper() == "TRUE"
        profiles.append(profile)

        courier = est.courier_by_id.get(ship["courier_id"])
        if courier and dep and arr and arr >= dep:
            if (arr - dep) > timedelta(hours=float(courier["sla_hours"])):
                j.uncertainties.append(
                    f"Shipment {ship['shipment_id']} took longer than the {courier['sla_hours']}-hour "
                    f"service level agreed with {courier['name']}, and is a likely cause of delay.")

        if profile["above_threshold"] and not profile["sensor_trustworthy"]:
            j.uncertainties.append(
                f"Shipment {ship['shipment_id']} has {profile['above_threshold']} temperature "
                f"reading(s) warmer than {EXCURSION_THRESHOLD_C}C, but none of them came from a "
                "sensor reporting good data quality. SOP-LOG-007 v7 requires a QA review rather "
                "than an automatic disposition.")
        if profile["flagged_by_logistics"] and profile["above_threshold"] == 0:
            j.uncertainties.append(
                f"Shipment {ship['shipment_id']} was flagged as a temperature excursion by logistics, "
                "but the telemetry contains nothing that supports it.")

    j.facts["custody.intact"] = reconcile(
        "custody.intact",
        [Assertion("LOGISTICS", custody_ok, True, None, "shipments.csv")])
    j.facts["custody.excursion_profiles"] = reconcile(
        "custody.excursion_profiles",
        [Assertion("TELEMETRY", profiles, True, None, "cryogenic_telemetry.csv")],
        "QA_RELEASE_APPROVER")

    # ---- manufacturing slot ---------------------------------------------------
    slots = est.slots_by_key.get(patient_key, [])
    if slots:
        slot = slots[0]
        agreed = slot["scheduler_state"] == "CONFIRMED" and slot["mes_state"] in {"READY", "PLANNED"}
        j.facts["slot.confirmed"] = reconcile("slot.confirmed", [
            Assertion("SCHEDULER", slot["scheduler_state"] == "CONFIRMED", False, slot.get("scheduled_start"), slot["slot_id"]),
            Assertion("MES", slot["mes_state"] not in {"CANCELLED"}, False, None, slot["slot_id"]),
        ])
        if slot["scheduler_state"] == "CONFIRMED" and slot["mes_state"] == "CANCELLED":
            j.blocking_reasons.append(
                f"Capacity: slot {slot['slot_id']} is confirmed in the scheduler but cancelled in "
                "MES, so the manufacturing capacity does not actually exist.")
        if not agreed:
            j.uncertainties.append(
                f"Capacity: slot {slot['slot_id']} is {phrase(slot['scheduler_state'])} in the "
                f"scheduler and {phrase(slot['mes_state'])} in MES.")

        shadow = est.shadow_priority_by_key.get(patient_key)
        if shadow and shadow["priority"] != slot["priority"]:
            j.shadow_signals.append(
                f"Priority: the scheduler holds {phrase(slot['priority'])} but the "
                f"PatientPriority_MASTER spreadsheet holds {phrase(shadow['priority'])} "
                f"(last changed by {shadow['updated_by'] or 'nobody recorded'}).")
        if shadow and shadow["updated_by"] in {"", "unknown"}:
            j.shadow_signals.append(
                "Priority: the spreadsheet change has no named decision maker, so it is not an "
                "acceptable basis for action.")

    # ---- manufacturing, QC, deviations, release -------------------------------
    batches = est.batches_by_key.get(patient_key, [])
    if batches:
        batch = batches[0]
        bid = batch["batch_id"]
        j.facts["batch.id"] = reconcile("batch.id", [Assertion("MES", bid, True, batch.get("mfg_start"), bid)])

        results = est.qc_by_batch.get(bid, [])
        reported = {r["assay"] for r in results}
        blocking = [r for r in results if r["result"] in BLOCKING_QC]
        oot = [r for r in results if r["result"] == "OOT"]
        missing = REQUIRED_ASSAYS - reported

        j.facts["qc.complete"] = reconcile("qc.complete", [
            Assertion("LIMS", not missing and not blocking, True, None, f"qc_results:{bid}")])
        j.facts["qc.summary"] = reconcile("qc.summary", [Assertion("LIMS", {
            "reported": len(results), "missing": sorted(missing),
            "blocking": [f"{r['assay']}={r['result']}" for r in blocking],
            "out_of_trend": [f"{r['assay']}={r['result']}" for r in oot],
        }, True, None, f"qc_results:{bid}")])

        open_devs = [d for d in est.deviations_by_batch.get(bid, []) if d["status"] != "CLOSED"]
        j.facts["deviations.open"] = reconcile("deviations.open", [
            Assertion("QMS", [d["deviation_id"] for d in open_devs], True, None, f"deviations:{bid}")])

        for dev in est.deviations_by_batch.get(bid, []):
            if dev["linked_event_id"] and dev["linked_event_id"] not in est.event_ids:
                j.uncertainties.append(
                    f"Audit trail: deviation {dev['deviation_id']} refers to event "
                    f"{dev['linked_event_id']}, which does not exist in the event store.")

        # The central correction. QMS is the only release authority; MES and ERP are advisory.
        j.facts["product.released"] = reconcile("product.released", [
            Assertion("QMS", batch["qms_release_status"] == "RELEASED", True, batch.get("mfg_end"), bid),
            Assertion("MES", batch["mes_status"] == "RELEASED", False, None, bid),
            Assertion("ERP", batch["erp_status"] == "AVAILABLE", False, None, bid),
        ], "QA_RELEASE_APPROVER")
        j.facts["mfg.state"] = reconcile("mfg.state", [Assertion("MES", batch["mes_status"], True, None, bid)])

        if batch["qms_release_status"] != "RELEASED":
            if batch["erp_status"] == "AVAILABLE" or batch["mes_status"] in {"RELEASED", "MFG_COMPLETE"}:
                j.uncertainties.append(
                    f"Release: MES reports {phrase(batch['mes_status'])} and ERP reports "
                    f"{phrase(batch['erp_status'])}, which suggest the product is available, but "
                    f"Quality has recorded {phrase(batch['qms_release_status'])} in the QMS. The "
                    "legacy product_ready() check would return true here; the QMS decision governs.")
        else:
            if blocking:
                detail = ", ".join(f"{phrase(r['assay'])} is {QC_RESULT_WORDS.get(r['result'], phrase(r['result']))}"
                                   for r in blocking)
                j.blocking_reasons.append(
                    f"Release integrity: batch {bid} was released by Quality while test results were "
                    f"still unresolved ({detail}).")
            if open_devs:
                j.blocking_reasons.append(
                    f"Release integrity: batch {bid} was released by Quality while deviation(s) "
                    f"{', '.join(d['deviation_id'] for d in open_devs)} were still open.")

    # ---- temporal integrity ---------------------------------------------------
    timeline = est.timeline(patient_key)
    for ev in timeline:
        occurred, recorded = parse_time(ev["occurred_at"]), parse_time(ev["recorded_at"])
        if occurred and recorded and (recorded - occurred) > timedelta(hours=6):
            j.uncertainties.append(
                f"Timing: event {ev['event_id']} was recorded "
                f"{round((recorded-occurred).total_seconds()/3600,1)} hours after it actually "
                "happened, so other systems may have acted on out-of-date information.")
    j.facts["timeline.events"] = reconcile(
        "timeline.events", [Assertion("EVENT_STORE", len(timeline), True, None, "events.jsonl")])

    j.state = derive_state(j, patient)
    return j


def derive_state(j: Journey, patient: dict) -> str:
    """Governed journey state. Never more optimistic than the evidence allows."""
    consent = j.value("consent.status")
    if consent == "WITHDRAWN":
        return "WITHDRAWN"
    if j.facts.get("identity.mrn_unique") and j.facts["identity.mrn_unique"].resolution is Resolution.UNRESOLVED:
        return "IDENTITY_UNRESOLVED"
    if any(j.facts[n].is_conflicted for n in ("identity.dob", "identity.mrn") if n in j.facts):
        return "IDENTITY_UNRESOLVED"
    if j.value("product.released") is True:
        return "QA_RELEASED" if not j.blocking_reasons else "RELEASE_INTEGRITY_REVIEW"
    if j.value("deviations.open"):
        return "QA_HOLD"
    if "qc.complete" in j.facts:
        return "QC_PENDING" if j.value("qc.complete") is False else "AWAITING_QA_RELEASE"
    if j.value("custody.intact") is False:
        return "CUSTODY_UNCERTAIN"
    return patient.get("journey_status", "UNKNOWN")
