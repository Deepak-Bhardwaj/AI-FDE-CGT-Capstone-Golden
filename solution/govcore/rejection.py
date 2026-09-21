"""A qualified person's decision not to release, with the reason they gave.

Until now a review had two possible endings: the gates blocked it, or it was approved. A
reviewer who read the evidence and decided against release had nowhere to say so. The
audit chain was therefore complete only for decisions that went forward, which is the half
that needs it least.

A rejection is recorded, attributed, timestamped and hash-chained like any other decision.
It blocks release deterministically - it is a quality disposition, not a note - and it
carries the reviewer's own words rather than a status code.

Only the person who recorded a rejection may withdraw it. A second reviewer who disagrees
records their own view; they do not erase a colleague's. There is deliberately no override:
see WHY_NO_OVERRIDE.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .audit import HashChain

STORE_PATH = Path(__file__).resolve().parents[1] / "evidence" / "rejections.jsonl"

RULE_ID = "R-QA-REJECTION"
RULE_VERSION = "1.0"

#: A rationale short enough to be a status code is not a rationale.
MIN_RATIONALE = 20

STANDING = "STANDING"
WITHDRAWN = "WITHDRAWN"

WHY_NO_OVERRIDE = (
    "A rejection cannot be overridden inside this system. Overriding a qualified person's "
    "recorded decision needs a third qualified person and a quality escalation procedure "
    "that does not exist here, and inventing one in software would be the wrong place to "
    "put it. A standing rejection whose author is unavailable is escalated as a quality "
    "matter, not resolved with a button."
)


class RejectionError(Exception):
    """Raised when a rejection is malformed, or withdrawn by someone who did not make it."""


@dataclass
class Rejection:
    rejection_id: str
    patient_key: str
    batch_id: str | None
    by: str
    authority: str
    rationale: str
    rejected_at: str
    blocking_at_the_time: list[str] = field(default_factory=list)
    recommendation_at_the_time: str = ""
    state: str = STANDING
    withdrawn_at: str | None = None
    withdrawn_by: str | None = None
    withdrawal_reason: str | None = None

    @property
    def standing(self) -> bool:
        return self.state == STANDING

    def as_dict(self) -> dict:
        return {**asdict(self), "standing": self.standing}


@dataclass
class RejectionStore:
    path: Path = STORE_PATH
    items: dict[str, Rejection] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ledger = HashChain(self.path)
        self._load()

    def _load(self) -> None:
        """Replay the ledger. A rejection that vanishes on restart is worse than none."""
        if not self.path.exists():
            return
        fields = set(Rejection.__dataclass_fields__)
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = entry.get("payload", entry)
            record = {k: v for k, v in payload.items() if k in fields}
            if "rejection_id" not in record:
                continue
            try:
                self.items[record["rejection_id"]] = Rejection(**record)
            except TypeError:
                continue

    def record(self, patient_key: str, by: str, authority: str, rationale: str,
               batch_id: str | None = None, blocking: list[str] | None = None,
               recommendation: str = "") -> Rejection:
        reason = (rationale or "").strip()
        if len(reason) < MIN_RATIONALE:
            raise RejectionError(
                f"A rejection must say why, in at least {MIN_RATIONALE} characters. The next "
                f"person to read this lot has only these words to work from.")
        if not by.strip():
            raise RejectionError("A rejection must name the person who made it.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rejection = Rejection(
            rejection_id=f"REJ-{len(self.items) + 1:05d}",
            patient_key=patient_key, batch_id=batch_id, by=by.strip(), authority=authority,
            rationale=reason, rejected_at=now,
            blocking_at_the_time=list(blocking or []),
            recommendation_at_the_time=recommendation)
        self.items[rejection.rejection_id] = rejection
        self.ledger.append("rejection", rejection.as_dict())
        return rejection

    def withdraw(self, rejection_id: str, by: str, reason: str) -> Rejection:
        rejection = self.items.get(rejection_id)
        if rejection is None:
            raise RejectionError(f"No rejection {rejection_id} exists.")
        if not rejection.standing:
            raise RejectionError(f"{rejection_id} was already withdrawn by "
                                 f"{rejection.withdrawn_by}.")
        if by.strip() != rejection.by:
            raise RejectionError(
                f"{rejection_id} was recorded by {rejection.by} and only they may withdraw "
                f"it. {WHY_NO_OVERRIDE}")
        note = (reason or "").strip()
        if len(note) < MIN_RATIONALE:
            raise RejectionError(
                f"Withdrawing a rejection must say what changed, in at least "
                f"{MIN_RATIONALE} characters.")
        rejection.state = WITHDRAWN
        rejection.withdrawn_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rejection.withdrawn_by = by.strip()
        rejection.withdrawal_reason = note
        self.ledger.append("rejection.withdrawn", rejection.as_dict())
        return rejection

    def standing_for(self, patient_key: str) -> list[Rejection]:
        return [r for r in self.items.values()
                if r.patient_key == patient_key and r.standing]

    def history_for(self, patient_key: str) -> list[Rejection]:
        """Withdrawn rejections stay visible. A reviewer changed their mind; that is evidence."""
        return sorted((r for r in self.items.values() if r.patient_key == patient_key),
                      key=lambda r: r.rejected_at)


STORE = RejectionStore()


def blocking_reason(rejection: Rejection) -> str:
    return (f"{rejection.by} ({rejection.authority}) rejected this batch on "
            f"{rejection.rejected_at[:10]}: {rejection.rationale}")
