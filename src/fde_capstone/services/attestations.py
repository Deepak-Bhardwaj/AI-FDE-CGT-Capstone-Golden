"""Signed human attestations, held beside the source systems rather than inside them.

When the authority that owns a gate states that the underlying evidence has been corrected in a
source system this service cannot write to, that statement is itself evidence: attributed,
signed, timestamped and reversible. It clears the gate provisionally and is always disclosed as
an attestation rather than a source-system record, so no one mistakes it for the real thing.

The raw files are never modified. Withdrawing an attestation returns the gate to what the
source data says.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STORE_PATH = Path(__file__).resolve().parents[1] / "evidence" / "attestations.jsonl"


@dataclass
class Attestation:
    attestation_id: str
    patient_key: str
    stage_id: str
    gate_ids: list[str]
    by: str
    role: str
    authority: str
    justification: str
    e_signature: str
    decision_id: str
    attested_at: str
    withdrawn_at: str | None = None
    withdrawn_by: str | None = None

    @property
    def live(self) -> bool:
        return self.withdrawn_at is None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AttestationStore:
    path: Path = STORE_PATH
    items: dict[str, Attestation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        """Replay the ledger, so a signed statement survives a restart of this service."""
        if not self.path.exists():
            return
        fields = set(Attestation.__dataclass_fields__)
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = {k: v for k, v in payload.items() if k in fields}
            if "attestation_id" not in record:
                continue
            try:
                self.items[record["attestation_id"]] = Attestation(**record)
            except TypeError:
                continue

    def record(self, **kwargs) -> Attestation:
        att = Attestation(attested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          **kwargs)
        self.items[att.attestation_id] = att
        self._append(att.as_dict())
        return att

    def withdraw(self, attestation_id: str, by: str) -> Attestation:
        att = self.items[attestation_id]
        att.withdrawn_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        att.withdrawn_by = by
        self._append({"event": "WITHDRAWN", **att.as_dict()})
        return att

    def live_by_gate(self, patient_key: str) -> dict[str, Attestation]:
        """Gate id -> the most recent live attestation covering it."""
        out: dict[str, Attestation] = {}
        for att in self.items.values():
            if att.patient_key != patient_key or not att.live:
                continue
            for gate_id in att.gate_ids:
                out[gate_id] = att
        return out

    def live_for_stage(self, patient_key: str, stage_id: str) -> Attestation | None:
        return next((a for a in reversed(list(self.items.values()))
                     if a.patient_key == patient_key and a.stage_id == stage_id and a.live), None)

    def _append(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")


STORE = AttestationStore()
