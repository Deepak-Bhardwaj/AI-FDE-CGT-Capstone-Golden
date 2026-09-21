"""Read-only access to the legacy estate.

Every file is opened in read mode. Nothing here writes to data/ or shadow_ops/.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
REF = ROOT / "data" / "reference"
SHADOW = ROOT / "shadow_ops"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def phrase(code: str | None, fallback: str = "not recorded") -> str:
    """Source-system code as readable prose, for operator-facing messages."""
    if not code:
        return fallback
    return str(code).replace("_", " ").lower()


class Estate:
    """Loaded snapshot of every source system."""

    def __init__(self) -> None:
        self.patients = _rows(RAW / "patients.csv")
        self.crm = _rows(RAW / "crm_patient_export.csv")
        self.clinical = _rows(RAW / "clinical_patient_export.csv")
        self.collections = _rows(RAW / "collections.csv")
        self.shipments = _rows(RAW / "shipments.csv")
        self.batches = _rows(RAW / "batches.csv")
        self.qc = _rows(RAW / "qc_results.csv")
        self.deviations = _rows(RAW / "deviations.csv")
        self.consents = _rows(RAW / "consents.csv")
        self.authorizations = _rows(RAW / "insurance_authorizations.csv")
        self.slots = _rows(RAW / "manufacturing_slots.csv")
        self.qualifications = _rows(RAW / "site_qualifications.csv")
        self.telemetry = _rows(RAW / "cryogenic_telemetry.csv")
        self.centers = _rows(REF / "treatment_centers.csv")
        self.couriers = _rows(REF / "couriers.csv")
        self.sites = _rows(REF / "manufacturing_sites.csv")
        self.products = _rows(REF / "products.csv")
        self.shadow_priority = _rows(SHADOW / "PatientPriority_MASTER.csv")
        self.shadow_slots = _rows(SHADOW / "ManufacturingSlots_FINAL_v7.csv")
        self.escalations = _rows(SHADOW / "CourierEscalations.csv")

        with (RAW / "events.jsonl").open(encoding="utf-8") as fh:
            self.events = [json.loads(line) for line in fh if line.strip()]

        self._index()

    def _index(self) -> None:
        self.by_key = {p["patient_key"]: p for p in self.patients}
        self.crm_by_key = {p["patient_key"]: p for p in self.crm}
        self.clinical_by_key = {p["patient_key"]: p for p in self.clinical}
        self.consent_by_key = {c["patient_key"]: c for c in self.consents}
        self.auth_by_key = {a["patient_key"]: a for a in self.authorizations}
        self.qual_by_center = {q["center_id"]: q for q in self.qualifications}
        self.center_by_id = {c["center_id"]: c for c in self.centers}
        self.courier_by_id = {c["courier_id"]: c for c in self.couriers}
        self.site_by_id = {s["site_id"]: s for s in self.sites}
        self.product_by_code = {p["product_code"]: p for p in self.products}
        self.shadow_priority_by_key = {x["patient_key"]: x for x in self.shadow_priority}

        self.collections_by_key = defaultdict(list)
        for row in self.collections:
            self.collections_by_key[row["patient_key"]].append(row)

        self.shipments_by_key = defaultdict(list)
        for row in self.shipments:
            self.shipments_by_key[row["patient_key"]].append(row)

        self.batches_by_key = defaultdict(list)
        for row in self.batches:
            self.batches_by_key[row["patient_key"]].append(row)

        self.slots_by_key = defaultdict(list)
        for row in self.slots:
            self.slots_by_key[row["patient_key"]].append(row)

        self.qc_by_batch = defaultdict(list)
        for row in self.qc:
            self.qc_by_batch[row["batch_id"]].append(row)

        self.deviations_by_batch = defaultdict(list)
        self.deviations_by_key = defaultdict(list)
        for row in self.deviations:
            self.deviations_by_batch[row["batch_id"]].append(row)
            self.deviations_by_key[row["patient_key"]].append(row)

        self.telemetry_by_shipment = defaultdict(list)
        for row in self.telemetry:
            self.telemetry_by_shipment[row["shipment_id"]].append(row)

        self.events_by_key = defaultdict(list)
        for row in self.events:
            self.events_by_key[row["patient_key"]].append(row)

        self.event_ids = {e["event_id"] for e in self.events}

        # MRN -> patients, for the duplicate-identifier check
        self.keys_by_mrn = defaultdict(list)
        for row in self.patients:
            self.keys_by_mrn[row["mrn"]].append(row["patient_key"])

    def timeline(self, patient_key: str, order_by: str = "occurred_at") -> list[dict]:
        """Journey history. Defaults to valid time, never ingestion time."""
        events = list(self.events_by_key.get(patient_key, []))
        events.sort(key=lambda e: (parse_time(e.get(order_by)) or datetime.min.replace(tzinfo=None).astimezone()))
        return events

    def emails(self) -> list[dict]:
        parsed = []
        for path in sorted((SHADOW / "emails").glob("*.eml")):
            text = path.read_text(encoding="utf-8", errors="replace")
            headers, _, body = text.partition("\n\n")
            meta = {"file": path.name, "body": body.strip()}
            for line in headers.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip().lower()] = val.strip()
            parsed.append(meta)
        return parsed


@lru_cache(maxsize=1)
def load() -> Estate:
    return Estate()
