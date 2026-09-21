"""Onboarding a patient the source systems do not know about yet.

This service is not the system of record. Registering someone here creates a provisional
record with its own identifier space (PR-nnnnn), never a P-nnnnn key, so nobody can mistake a
control-tower registration for a CRM or clinical enrolment. The record carries who registered
it, when, from what referral, and what it must still be reconciled against.

If the details look like someone already in the estate, the registration is held for identity
adjudication rather than created. A duplicate patient record is a wrong-patient risk.
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .loader import Estate, load

STORE_PATH = Path(__file__).resolve().parents[1] / "evidence" / "registrations.jsonl"

PROVISIONAL = "PROVISIONAL"
NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"
CONFIRMED = "CONFIRMED"
REJECTED = "REJECTED"

# Provisional numbers are issued in their own 9xxxxx block so they are recognisable on sight
# and cannot collide with a number the source systems issued.
MRN_PREFIX = "MRN-9"
DOB_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RegistrationError(ValueError):
    """The submission cannot be accepted as it stands."""


@dataclass
class Registration:
    registration_id: str
    full_name: str
    dob: str
    mrn: str
    center_id: str
    product_code: str
    referral_source: str
    planned_enrolment: str
    registered_by: str
    registered_at: str
    status: str
    duplicate_candidates: list[dict] = field(default_factory=list)
    decided_by: str | None = None
    decided_at: str | None = None
    decision_reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def duplicate_candidates(dob: str, mrn: str, full_name: str, est: Estate) -> list[dict]:
    """Anyone already in the estate who could be this person. Matching is deliberately loose."""
    name = full_name.strip().lower()
    hits = []
    for patient in est.patients:
        reasons = []
        if mrn and patient["mrn"] == mrn:
            reasons.append("same medical record number")
        if dob and patient["dob"] == dob:
            reasons.append("same date of birth")
        if name and (patient.get("synthetic_name") or "").strip().lower() == name:
            reasons.append("same name")
        if reasons:
            hits.append({"patient_key": patient["patient_key"], "matched_on": reasons,
                         "center_id": patient["center_id"],
                         "journey_status": patient["journey_status"]})
    return hits


class RegistrationStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self.items: dict[str, Registration] = {}
        self._load()

    def _load(self) -> None:
        """Replay the ledger. Without this a restart reissues PR-00001 to a different person."""
        if not self.path.exists():
            return
        fields = set(Registration.__dataclass_fields__)
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = {k: v for k, v in payload.items() if k in fields}
            if "registration_id" not in record:
                continue
            try:
                self.items[record["registration_id"]] = Registration(**record)
            except TypeError:
                continue

    def next_id(self) -> str:
        highest = 0
        for existing in self.items:
            _, _, digits = existing.partition("-")
            if digits.isdigit():
                highest = max(highest, int(digits))
        return f"PR-{highest + 1:05d}"

    def issue_mrn(self, est: Estate) -> str:
        """A provisional number, checked against the estate and everything issued here."""
        taken = set(est.keys_by_mrn) | {r.mrn for r in self.items.values()}
        for _ in range(100):
            candidate = f"{MRN_PREFIX}{secrets.randbelow(100000):05d}"
            if candidate not in taken:
                return candidate
        raise RegistrationError("could not issue a provisional medical record number")

    def register(self, payload: dict, registered_by: str, est: Estate) -> Registration:
        name = (payload.get("full_name") or "").strip()
        dob = (payload.get("dob") or "").strip()
        centre = (payload.get("center_id") or "").strip().upper()
        product = (payload.get("product_code") or "").strip().upper()
        referral = (payload.get("referral_source") or "").strip()
        planned = (payload.get("planned_enrolment") or "").strip()

        if len(name.split()) < 2:
            raise RegistrationError("a full name is required")
        if not DOB_PATTERN.match(dob):
            raise RegistrationError("date of birth must be in the form 1980-02-21")
        if centre not in est.center_by_id:
            raise RegistrationError(f"'{centre}' is not a treatment centre in the reference data")
        if product not in est.product_by_code:
            raise RegistrationError(f"'{product}' is not a product in the reference data")
        if not referral:
            raise RegistrationError("the referral source must be recorded")
        if not DOB_PATTERN.match(planned):
            raise RegistrationError("a planned enrolment date is required")

        candidates = duplicate_candidates(dob, "", name, est)
        registration = Registration(
            registration_id=self.next_id(), full_name=name, dob=dob,
            mrn=self.issue_mrn(est),
            center_id=centre, product_code=product, referral_source=referral,
            planned_enrolment=planned, registered_by=registered_by,
            registered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status=NEEDS_ADJUDICATION if candidates else PROVISIONAL,
            duplicate_candidates=candidates)
        self.items[registration.registration_id] = registration
        self._append(registration.as_dict())
        return registration

    def decide(self, registration_id: str, decision: str, decided_by: str,
               reason: str) -> Registration:
        registration = self.items.get(registration_id)
        if registration is None:
            raise RegistrationError(f"'{registration_id}' is not a registration on record")
        if registration.status != NEEDS_ADJUDICATION:
            raise RegistrationError("only a held registration can be adjudicated")
        if decision not in (CONFIRMED, REJECTED):
            raise RegistrationError("decision must be CONFIRMED or REJECTED")
        registration.status = PROVISIONAL if decision == CONFIRMED else REJECTED
        registration.decided_by = decided_by
        registration.decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        registration.decision_reason = reason
        self._append({"event": decision, **registration.as_dict()})
        return registration

    def all(self) -> list[dict]:
        return [r.as_dict() for r in self.items.values()][::-1]

    def _append(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")


STORE = RegistrationStore()


def reference_data(estate: Estate | None = None) -> dict:
    est = estate or load()
    return {
        "centres": [{"center_id": c["center_id"], "name": c["canonical_name"],
                     "country": c["country"], "qualification": c["qualification_status"]}
                    for c in est.centers],
        "products": [{"product_code": p["product_code"], "name": p["therapy_family"],
                      "indication": p["indication"],
                      "target_v2v_days": p["target_v2v_days"]}
                     for p in est.products],
    }
