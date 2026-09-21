"""Append-only, hash-chained evidence.

An audit that only lives in memory is not an audit: a restart erases it and nothing can prove
what was lost. Every record here is written at the moment it is made and chained to the one
before it, so a deleted, reordered or edited record breaks the chain at a nameable position
rather than disappearing quietly.

The chain answers two different questions. verify() asks whether this file is internally
consistent. completeness() asks whether the records still point at source rows that exist - a
chain can be perfectly valid and still describe a world that has moved.

Event time and recording time are kept apart. decided_at is when the decision was made;
recorded_at is when this service learned of it. They are not the same fact.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import telemetry
from .types import Decision

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
DEFAULT_PATH = EVIDENCE / "decision_audit.jsonl"
ACCESS_PATH = EVIDENCE / "access_audit.jsonl"

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(seq: int, recorded_at: str, prev_hash: str, payload: dict) -> str:
    raw = f"{seq}|{recorded_at}|{prev_hash}|{_canonical(payload)}".encode()
    return hashlib.sha256(raw).hexdigest()


class HashChain:
    """A JSONL file where every line commits to the line before it.

    Only the length and the head hash are held in memory. History is streamed from disk when
    something actually needs it, so a long-lived ledger does not become a memory cost.
    """

    def __init__(self, path: Path, snapshot: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot:
            self.path.write_text("", encoding="utf-8")
            self._count, self._head = 0, GENESIS
        else:
            self._count, self._head = self._resume()

    def _stream(self):
        """Yield every record in order, without keeping any of them."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for index, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # A line that will not parse is evidence of tampering, not a reason to stop.
                    yield {"seq": index, "malformed": line[:200]}

    def _resume(self) -> tuple[int, str]:
        count, head = 0, GENESIS
        for entry in self._stream():
            count += 1
            head = entry.get("entry_hash", head)
        return count, head

    @property
    def head(self) -> str:
        return self._head

    def append(self, kind: str, payload: dict) -> dict:
        seq, recorded_at, prev_hash = self._count, _now(), self._head
        entry = {"seq": seq, "kind": kind, "recorded_at": recorded_at, "prev_hash": prev_hash,
                 "correlation_id": telemetry.current_id(),
                 "entry_hash": entry_hash(seq, recorded_at, prev_hash, payload),
                 "payload": payload}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
        self._count, self._head = seq + 1, entry["entry_hash"]
        return entry

    def verify(self) -> dict:
        """Recompute the chain from disk and name the first place it stops adding up."""
        prev_hash = GENESIS
        index = -1
        for index, entry in enumerate(self._stream()):
            divergence = None
            if "malformed" in entry:
                divergence = "the record could not be parsed"
            elif entry.get("seq") != index:
                divergence = f"sequence is {entry.get('seq')} where {index} was expected"
            elif entry.get("prev_hash") != prev_hash:
                divergence = "this record does not follow the one before it"
            elif entry_hash(entry["seq"], entry["recorded_at"], entry["prev_hash"],
                            entry["payload"]) != entry.get("entry_hash"):
                divergence = "the record has been altered since it was written"
            if divergence:
                return {"entries": self._count, "chain_valid": False,
                        "first_divergence": {"seq": index, "reason": divergence},
                        "head": self._head, "path": self.path.name}
            prev_hash = entry["entry_hash"]
        return {"entries": index + 1, "chain_valid": True, "first_divergence": None,
                "head": self._head, "path": self.path.name}

    @property
    def entries(self) -> list[dict]:
        return list(self._stream())

    def payloads(self) -> list[dict]:
        return [e["payload"] for e in self._stream() if "payload" in e]

    def recent(self, limit: int = 50) -> list[dict]:
        tail: list[dict] = []
        for entry in self._stream():
            if "payload" not in entry:
                continue
            tail.append({**entry["payload"], "seq": entry["seq"],
                         "recorded_at": entry["recorded_at"],
                         "correlation_id": entry.get("correlation_id")})
            if len(tail) > limit:
                tail.pop(0)
        return tail[::-1]

    def by_correlation(self, correlation_id: str) -> list[dict]:
        """Everything one request caused, in the order it caused it."""
        return [{**e["payload"], "seq": e["seq"], "kind": e.get("kind"),
                 "recorded_at": e["recorded_at"]}
                for e in self._stream()
                if e.get("correlation_id") == correlation_id and "payload" in e]

    def __len__(self) -> int:
        return self._count


class AuditLog:
    """Decision ledger. Written at the moment of the decision, never rewritten.

    Decisions are few and are queried on the request path, so their payloads are also held in
    memory. The chain on disk stays the authority; this is an index over it, rebuilt at startup
    rather than trusted across restarts.
    """

    def __init__(self, path: Path | None = None, snapshot: bool = False) -> None:
        self.chain = HashChain(Path(path or DEFAULT_PATH), snapshot=snapshot)
        self._payloads: list[dict] = [] if snapshot else self.chain.payloads()

    @property
    def path(self) -> Path:
        return self.chain.path

    def record(self, decision: Decision) -> Decision:
        payload = decision.as_dict()
        self.chain.append("decision", payload)
        self._payloads.append(payload)
        return decision

    def verify(self) -> dict:
        return self.chain.verify()

    def completeness(self, known_subjects: set[str]) -> dict:
        """A valid chain can still name subjects the source data no longer contains. DOC-042."""
        dangling = []
        for seq, payload in enumerate(self._payloads):
            for value in (payload.get("subject") or {}).values():
                if isinstance(value, str) and value.startswith("P-") and value not in known_subjects:
                    dangling.append({"seq": seq, "subject": value})
        return {"checked": len(self._payloads), "dangling": dangling, "complete": not dangling,
                "note": "Every recorded decision still resolves to a source row." if not dangling
                        else "Some decisions name subjects the source data no longer contains."}

    def flush(self) -> Path:
        """Records are already durable; kept so callers can name the artefact they produced."""
        return self.chain.path

    def __len__(self) -> int:
        return len(self.chain)

    @property
    def records(self) -> list[dict]:
        return list(self._payloads)
