"""Patient identifier reconciliation across CRM, clinical and orchestration sources.

Never fabricates a patient/material/batch linkage. Attribute conflicts (for
example disagreeing DOB on the same ``patient_key``) are returned as evidence
and require human review. Identifiers that point at different ``patient_key``
values are not merged.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..source_cases import BASELINE

RULE_VERSION = "patient-resolver-v1"
AUTHORITY_COI = "human-chain-of-identity"

COMPARE_FIELDS = ("dob", "mrn", "center_id")

ORCH_PATH = Path("data/raw/patients.csv")
CRM_PATH = Path("data/raw/crm_patient_export.csv")
CLINICAL_PATH = Path("data/raw/clinical_patient_export.csv")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _norm(value: Any) -> str:
    return str(value or "").strip()


class PatientResolver:
    """Reconcile CRM, clinical and orchestration identifiers from local CSV evidence."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else BASELINE
        self._orch_by_key = {row["patient_key"]: row for row in _read_csv(self.root / ORCH_PATH)}
        self._crm_by_key = {row["patient_key"]: row for row in _read_csv(self.root / CRM_PATH)}
        self._clinical_by_key = {
            row["patient_key"]: row for row in _read_csv(self.root / CLINICAL_PATH)
        }
        self._keys_by_crm = self._index(self._orch_by_key.values(), "crm_patient_id")
        self._keys_by_clinical = self._index(self._orch_by_key.values(), "clinical_subject_id")
        self._keys_by_mrn = self._index(self._orch_by_key.values(), "mrn")

    @staticmethod
    def _index(rows: Iterable[Mapping[str, str]], field: str) -> dict[str, list[str]]:
        index: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            value = _norm(row.get(field))
            key = _norm(row.get("patient_key"))
            if value and key and key not in index[value]:
                index[value].append(key)
        return index

    def resolve(
        self,
        orchestration_id: str | None = None,
        crm_id: str | None = None,
        clinical_id: str | None = None,
        mrn: str | None = None,
    ) -> dict[str, Any]:
        """Return an evidence-bearing identity resolution.

        Required keys: ``resolved_patient_key``, ``confidence_score``,
        ``evidence``, ``requires_human_review``.
        """
        evidence: list[dict[str, str]] = []
        candidate_sets: list[tuple[str, set[str]]] = []

        orch_id = _norm(orchestration_id)
        crm = _norm(crm_id)
        clinical = _norm(clinical_id)
        mrn_value = _norm(mrn)

        if orch_id:
            keys = {orch_id} if orch_id in self._orch_by_key else set()
            candidate_sets.append(("ORCHESTRATION_ID", keys))
            evidence.append(self._id_evidence("orchestration", str(ORCH_PATH), orch_id, "patient_key", orch_id))
        if crm:
            keys = set(self._keys_by_crm.get(crm, []))
            candidate_sets.append(("CRM_ID", keys))
            evidence.append(self._id_evidence("CRM", str(CRM_PATH), crm, "crm_patient_id", crm))
        if clinical:
            keys = set(self._keys_by_clinical.get(clinical, []))
            candidate_sets.append(("CLINICAL_ID", keys))
            evidence.append(
                self._id_evidence("clinical", str(CLINICAL_PATH), clinical, "clinical_subject_id", clinical)
            )
        if mrn_value:
            keys = set(self._keys_by_mrn.get(mrn_value, []))
            candidate_sets.append(("MRN", keys))
            evidence.append(self._id_evidence("orchestration", str(ORCH_PATH), mrn_value, "mrn", mrn_value))

        if not candidate_sets:
            return self._result(
                "",
                0.0,
                evidence,
                True,
                conflicts=[{"type": "no_identifier_supplied"}],
            )

        non_empty = [keys for _, keys in candidate_sets if keys]
        if not non_empty:
            return self._result(
                "",
                0.0,
                evidence,
                True,
                conflicts=[{"type": "identifier_not_found", "inputs": [label for label, _ in candidate_sets]}],
            )

        missed = [label for label, keys in candidate_sets if not keys]
        union = set.union(*non_empty)
        intersection = set.intersection(*non_empty)
        if missed and len(union) == 1:
            scored = self._score_record(next(iter(union)), evidence)
            scored["requires_human_review"] = True
            scored["confidence_score"] = min(float(scored["confidence_score"]), 0.3)
            scored["authority_requirement"] = AUTHORITY_COI
            scored["conflicts"] = list(scored.get("conflicts") or []) + [
                {"type": "identifier_not_found", "inputs": missed}
            ]
            return scored
        if len(union) > 1:
            return self._result(
                "",
                0.0,
                evidence,
                True,
                conflicts=[
                    {
                        "type": "identifier_collision",
                        "patient_keys": sorted(union),
                        "note": "Identifiers point at more than one patient_key; no linkage was fabricated.",
                    }
                ],
            )

        patient_key = next(iter(intersection if intersection else union))
        return self._score_record(patient_key, evidence)

    def _score_record(self, patient_key: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
        orch = self._orch_by_key.get(patient_key)
        crm = self._crm_by_key.get(patient_key)
        clinical = self._clinical_by_key.get(patient_key)
        sources = {
            "orchestration": (orch, str(ORCH_PATH)),
            "CRM": (crm, str(CRM_PATH)),
            "clinical": (clinical, str(CLINICAL_PATH)),
        }
        conflicts: list[dict[str, Any]] = []
        present = 0
        for source, (row, path) in sources.items():
            if not row:
                conflicts.append({"type": "missing_source", "source": source, "patient_key": patient_key})
                continue
            present += 1
            for field in COMPARE_FIELDS:
                evidence.append(
                    {
                        "source": source,
                        "path": path.replace("\\", "/"),
                        "patient_key": patient_key,
                        "field": field,
                        "value": _norm(row.get(field)),
                    }
                )

        for field in COMPARE_FIELDS:
            values = {}
            for source, (row, _) in sources.items():
                if row and field in row:
                    values[source] = _norm(row.get(field))
            distinct = {value for value in values.values() if value}
            if len(distinct) > 1:
                conflicts.append(
                    {
                        "type": "attribute_conflict",
                        "field": field,
                        "values": values,
                        "patient_key": patient_key,
                    }
                )

        mrn = _norm((orch or {}).get("mrn"))
        mrn_keys = self._keys_by_mrn.get(mrn, [])
        if mrn and len(mrn_keys) > 1:
            conflicts.append(
                {
                    "type": "duplicate_mrn",
                    "mrn": mrn,
                    "patient_keys": mrn_keys,
                }
            )

        attribute_conflicts = [c for c in conflicts if c.get("type") == "attribute_conflict"]
        duplicate_mrn = any(c.get("type") == "duplicate_mrn" for c in conflicts)
        missing = any(c.get("type") == "missing_source" for c in conflicts)

        if attribute_conflicts or duplicate_mrn:
            confidence = 0.55 if len(attribute_conflicts) == 1 and not duplicate_mrn else 0.35
            if duplicate_mrn and attribute_conflicts:
                confidence = 0.25
            return self._result(patient_key, confidence, evidence, True, conflicts=conflicts)

        if present < 3 or missing:
            return self._result(patient_key, 0.4, evidence, True, conflicts=conflicts)

        return self._result(patient_key, 0.95, evidence, False, conflicts=conflicts)

    @staticmethod
    def _id_evidence(source: str, path: str, record: str, field: str, value: str) -> dict[str, str]:
        return {
            "source": source,
            "path": path.replace("\\", "/"),
            "patient_key": record,
            "field": field,
            "value": value,
        }

    @staticmethod
    def _result(
        resolved_patient_key: str,
        confidence_score: float,
        evidence: list[dict[str, str]],
        requires_human_review: bool,
        conflicts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "resolved_patient_key": resolved_patient_key,
            "confidence_score": confidence_score,
            "evidence": evidence,
            "requires_human_review": requires_human_review,
            "conflicts": conflicts or [],
            "authority_requirement": AUTHORITY_COI if requires_human_review else "none",
            "rule_version": RULE_VERSION,
        }


def resolve_patient(
    orchestration_id: str | None = None,
    crm_id: str | None = None,
    clinical_id: str | None = None,
    mrn: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Module-level helper used by CLI and API."""
    return PatientResolver(root=root).resolve(
        orchestration_id=orchestration_id,
        crm_id=crm_id,
        clinical_id=clinical_id,
        mrn=mrn,
    )
