"""Cross-system exception intelligence (POC 2).

Deterministic observe/correlate/recommend only. Never updates patient, batch,
QMS, or shipment state. Every exception sets ``requires_human_review=True``.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..source_cases import BASELINE

RULE_VERSION = "exception-detector-v1"


def _db_path(database_path: str | None = None) -> Path:
    if database_path:
        return Path(database_path)
    return BASELINE / "data" / "cgt_legacy.db"


def _rows(con: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def _exception(
    exception_id: str,
    patient_key: str,
    exception_type: str,
    severity: str,
    conflicting_systems: list[str],
    evidence: list[dict[str, Any]],
    recommendation: str,
) -> dict[str, Any]:
    return {
        "exception_id": exception_id,
        "patient_id": patient_key,
        "exception_type": exception_type,
        "severity": severity,
        "conflicting_systems": conflicting_systems,
        "evidence": evidence,
        "recommendation": recommendation,
        "requires_human_review": True,
        "authority_requirement": "human-qa-or-coi",
        "rule_version": RULE_VERSION,
        "autonomous_action": "none",
    }


def detect_exceptions(database_path: str | None = None) -> list[dict[str, Any]]:
    """Return ranked cross-system contradictions from the local estate.

    SQLite tables are optional. Missing tables skip that detector; CSV identity
    collisions still fire from the frozen source baseline.
    """
    path = str(_db_path(database_path))
    found: list[dict[str, Any]] = []
    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(path)
        detectors = (
            _mes_qms_conflicts,
            _slot_conflicts,
            _impossible_shipments,
            _withdrawn_consent_in_flight,
            _open_deviations,
            _expired_site_controls,
        )
        for detector in detectors:
            try:
                found.extend(detector(con))
            except sqlite3.OperationalError:
                continue
    except sqlite3.Error:
        pass
    finally:
        if con is not None:
            con.close()
    try:
        found.extend(_duplicate_mrns())
    except FileNotFoundError:
        pass
    order = {"CRITICAL": 0, "HIGH": 1, "MAJOR": 2, "MEDIUM": 3, "LOW": 4}
    found.sort(key=lambda row: (order.get(row["severity"], 9), row["patient_id"], row["exception_id"]))
    return found


def detect_for_patient(patient_key: str, database_path: str | None = None) -> list[dict[str, Any]]:
    return [row for row in detect_exceptions(database_path) if row["patient_id"] == patient_key]


def _mes_qms_conflicts(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _rows(
        con,
        """
        SELECT batch_id, patient_key, mes_status, qms_release_status, erp_status
        FROM batches
        WHERE mes_status = 'RELEASED' AND qms_release_status != 'RELEASED'
        """,
    )
    out = []
    for row in rows:
        out.append(
            _exception(
                f"EXC-MES-QMS-{row['batch_id']}",
                row["patient_key"],
                "MES_RELEASED_QMS_NOT_RELEASED",
                "HIGH",
                ["MES", "QMS", "ERP"],
                [
                    {"field": "batch_id", "value": row["batch_id"]},
                    {"field": "mes_status", "value": row["mes_status"]},
                    {"field": "qms_release_status", "value": row["qms_release_status"]},
                    {"field": "erp_status", "value": row["erp_status"]},
                    {"policy": "SOP-QA-014-v4", "note": "Manufacturing completion is not product release."},
                ],
                "Hold return logistics and infusion. QA must dispose the batch; do not treat MES RELEASED as QA release.",
            )
        )
    return out


def _slot_conflicts(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _rows(
        con,
        """
        SELECT slot_id, patient_key, scheduler_state, mes_state, site_id
        FROM manufacturing_slots
        WHERE scheduler_state = 'CONFIRMED' AND mes_state = 'CANCELLED'
        """,
    )
    out = []
    for row in rows:
        out.append(
            _exception(
                f"EXC-SLOT-{row['slot_id']}",
                row["patient_key"],
                "SCHEDULER_CONFIRMED_MES_CANCELLED",
                "HIGH",
                ["SCHEDULER", "MES"],
                [
                    {"field": "slot_id", "value": row["slot_id"]},
                    {"field": "site_id", "value": row["site_id"]},
                    {"field": "scheduler_state", "value": row["scheduler_state"]},
                    {"field": "mes_state", "value": row["mes_state"]},
                ],
                "Reconcile scheduler vs MES before treating the slot as capacity. Do not auto-rebook.",
            )
        )
    return out


def _impossible_shipments(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _rows(
        con,
        """
        SELECT shipment_id, patient_key, direction, departed_at, arrived_at, status
        FROM shipments
        WHERE arrived_at IS NOT NULL AND departed_at IS NOT NULL AND arrived_at < departed_at
        """,
    )
    out = []
    for row in rows:
        out.append(
            _exception(
                f"EXC-TIME-{row['shipment_id']}",
                row["patient_key"],
                "IMPOSSIBLE_SHIPMENT_TIMELINE",
                "HIGH",
                ["LOGISTICS"],
                [
                    {"field": "shipment_id", "value": row["shipment_id"]},
                    {"field": "direction", "value": row["direction"]},
                    {"field": "departed_at", "value": row["departed_at"]},
                    {"field": "arrived_at", "value": row["arrived_at"]},
                    {"field": "status", "value": row["status"]},
                    {"note": "Event time contradiction; do not assume latest timestamp is latest real-world event."},
                ],
                "Do not invent a corrected timeline. Quality/logistics must adjudicate source timestamps.",
            )
        )
    return out


def _withdrawn_consent_in_flight(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _rows(
        con,
        """
        SELECT c.consent_id, c.patient_key, c.status AS consent_status, p.journey_status
        FROM consents c
        JOIN patients p ON p.patient_key = c.patient_key
        WHERE c.status IN ('WITHDRAWN', 'EXPIRED_VERSION')
          AND p.journey_status NOT IN ('ENROLLED', 'ELIGIBLE')
        """,
    )
    out = []
    for row in rows:
        out.append(
            _exception(
                f"EXC-CONSENT-{row['consent_id']}",
                row["patient_key"],
                "CONSENT_BLOCKING_IN_FLIGHT_JOURNEY",
                "CRITICAL",
                ["CLINICAL", "ORCHESTRATION"],
                [
                    {"field": "consent_id", "value": row["consent_id"]},
                    {"field": "consent_status", "value": row["consent_status"]},
                    {"field": "journey_status", "value": row["journey_status"]},
                    {"eval": "EVAL-004", "note": "No autonomous consequential continuation."},
                ],
                "Halt downstream manufacturing/release/infusion recommendations. Clinical + QA HITL required.",
            )
        )
    return out


def _open_deviations(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _rows(
        con,
        """
        SELECT deviation_id, patient_key, batch_id, type, severity, status
        FROM deviations
        WHERE status IN ('OPEN', 'INVESTIGATING')
        """,
    )
    out = []
    for row in rows:
        sev = "CRITICAL" if str(row.get("severity") or "").upper() == "CRITICAL" else "MAJOR"
        out.append(
            _exception(
                f"EXC-DEV-{row['deviation_id']}",
                row["patient_key"],
                "OPEN_QUALITY_DEVIATION",
                sev,
                ["QMS"],
                [
                    {"field": "deviation_id", "value": row["deviation_id"]},
                    {"field": "batch_id", "value": row["batch_id"]},
                    {"field": "type", "value": row["type"]},
                    {"field": "qms_status", "value": row["status"]},
                    {"field": "recorded_severity", "value": row["severity"]},
                ],
                "Blocking input to QA release. Do not auto-close or auto-release.",
            )
        )
    return out


def _expired_site_controls(con: sqlite3.Connection) -> list[dict[str, Any]]:
    sites = _rows(
        con,
        """
        SELECT center_id, training_status, equipment_status, quality_agreement, system_status
        FROM site_qualifications
        WHERE training_status = 'EXPIRED' OR equipment_status = 'DUE'
        """,
    )
    out = []
    for site in sites:
        patients = _rows(
            con,
            """
            SELECT patient_key, journey_status FROM patients
            WHERE center_id = ?
              AND journey_status IN ('APHERESIS_PENDING', 'ELIGIBLE', 'ENROLLED', 'COLLECTED')
            """,
            (site["center_id"],),
        )
        for patient in patients[:8]:
            out.append(
                _exception(
                    f"EXC-SITE-{site['center_id']}-{patient['patient_key']}",
                    patient["patient_key"],
                    "SITE_QUALIFICATION_EXPIRED_OR_DUE",
                    "HIGH",
                    ["TREATMENT_CENTER", "QUALITY"],
                    [
                        {"field": "center_id", "value": site["center_id"]},
                        {"field": "training_status", "value": site["training_status"]},
                        {"field": "equipment_status", "value": site["equipment_status"]},
                        {"field": "journey_status", "value": patient["journey_status"]},
                        {"inject": "INJ-005"},
                    ],
                    "Revalidate site qualification before collection or downstream clinical milestones.",
                )
            )
    return out


def _duplicate_mrns() -> list[dict[str, Any]]:
    """Identity collisions from CSV evidence, not SQLite projection.

    SQLite can drop or reshape identifier disagreements. POC 1 reads the same
    CSVs; POC 2 must not treat ``data/cgt_legacy.db`` as the identity source.
    """
    path = BASELINE / "data" / "raw" / "patients.csv"
    by_mrn: dict[str, list[dict[str, str]]] = defaultdict(list)
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mrn = (row.get("mrn") or "").strip()
            if mrn:
                by_mrn[mrn].append(row)
    out = []
    for mrn, people in sorted(by_mrn.items()):
        if len(people) < 2:
            continue
        keys = [p["patient_key"] for p in people]
        for person in people:
            out.append(
                _exception(
                    f"EXC-MRN-{mrn}-{person['patient_key']}",
                    person["patient_key"],
                    "DUPLICATE_MRN_IDENTITY_COLLISION",
                    "CRITICAL",
                    ["CRM", "CLINICAL", "ORCHESTRATION"],
                    [
                        {"field": "mrn", "value": mrn},
                        {"field": "colliding_patient_keys", "value": keys},
                        {"field": "dob", "value": person.get("dob")},
                        {"source": "data/raw/patients.csv"},
                        {
                            "eval": "EVAL-002 / INJ-007",
                            "note": "Do not fabricate a single patient from a shared MRN.",
                        },
                    ],
                    "Chain-of-identity HITL. Do not merge records. Use /identity/resolve for evidence pack.",
                )
            )
    return out
