"""Two-person approval for consequential actions.

A qualified person may propose a release. A second, different qualified person must
countersign it before anything executes. Neither half is sufficient on its own, so the
never-event named in the charter - an unsupervised batch release - cannot be reached by a
single account, a single session or a single mistake.

The typed signature phrase is never stored. What is kept is a binding of the signer to the
approval they signed, so a signature lifted from one record cannot be replayed onto another.

The store is append-only. A withdrawn or expired request stays on the record.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .authority import Countersignature

STORE_PATH = Path(__file__).resolve().parents[1] / "evidence" / "dual_control.jsonl"

# A pending release is a standing invitation to act on a living patient's material. It expires
# so that a stale approval cannot be countersigned days later against changed evidence.
VALIDITY_SECONDS = 30 * 60
MIN_PHRASE_LENGTH = 4


class DualControlError(PermissionError):
    """Raised when a two-person approval cannot proceed as requested."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def sign(identity: str, approval_id: str, phrase: str) -> str:
    """Bind a signer to one approval. The phrase itself is discarded."""
    raw = f"{identity}|{approval_id}|{phrase}".encode()
    return "sig:" + hashlib.sha256(raw).hexdigest()


class ApprovalState:
    AWAITING = "AWAITING_COUNTERSIGNATURE"
    COMPLETED = "COUNTERSIGNED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


@dataclass
class Approval:
    approval_id: str
    action: str
    subject: str
    decision_id: str
    justification: str
    first_by: str
    first_role: str
    first_signature: str
    first_at: str
    expires_at: str
    context: dict = field(default_factory=dict)
    state: str = ApprovalState.AWAITING
    second_by: str | None = None
    second_role: str | None = None
    second_signature: str | None = None
    second_at: str | None = None
    closed_reason: str | None = None

    def expired(self, at: datetime | None = None) -> bool:
        return (at or _now()) > datetime.fromisoformat(self.expires_at)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApprovalStore:
    path: Path = STORE_PATH
    items: dict[str, Approval] = field(default_factory=dict)

    def request(self, action: str, subject: str, decision_id: str, approver: str, role: str,
                phrase: str, justification: str, context: dict | None = None) -> Approval:
        if not (phrase or "").strip() or len(phrase.strip()) < MIN_PHRASE_LENGTH:
            raise DualControlError(
                f"an electronic signature of at least {MIN_PHRASE_LENGTH} characters is required")
        approval_id = "APR-" + secrets.token_hex(6).upper()
        started = _now()
        approval = Approval(
            approval_id=approval_id, action=action, subject=subject, decision_id=decision_id,
            justification=justification.strip(), first_by=approver, first_role=role,
            first_signature=sign(approver, approval_id, phrase.strip()),
            first_at=_stamp(started),
            expires_at=_stamp(started + timedelta(seconds=VALIDITY_SECONDS)),
            context=dict(context or {}))
        self.items[approval_id] = approval
        self._append("REQUESTED", approval)
        return approval

    def countersign(self, approval_id: str, approver: str, role: str, phrase: str) -> Approval:
        approval = self.items.get(approval_id)
        if approval is None:
            raise DualControlError(f"no approval is open as '{approval_id}'")
        if approval.state == ApprovalState.COMPLETED:
            raise DualControlError(
                f"{approval_id} was already countersigned by {approval.second_by}")
        if approval.state != ApprovalState.AWAITING:
            raise DualControlError(f"{approval_id} is {approval.state.lower()} and cannot be signed")
        if approval.expired():
            approval.state = ApprovalState.EXPIRED
            approval.closed_reason = "the approval window closed before a second approver signed"
            self._append("EXPIRED", approval)
            raise DualControlError(
                f"{approval_id} expired at {approval.expires_at}; the first approver must start again")
        if approver == approval.first_by:
            raise DualControlError(
                f"{approver} requested this approval and cannot also countersign it; "
                "a second approver holding the same authority must sign")
        if role != approval.first_role:
            raise DualControlError(
                f"countersigning '{approval.action}' requires the {approval.first_role} authority; "
                f"{approver} holds {role}")
        if not (phrase or "").strip() or len(phrase.strip()) < MIN_PHRASE_LENGTH:
            raise DualControlError(
                f"an electronic signature of at least {MIN_PHRASE_LENGTH} characters is required")

        approval.second_by = approver
        approval.second_role = role
        approval.second_signature = sign(approver, approval_id, phrase.strip())
        approval.second_at = _stamp(_now())
        approval.state = ApprovalState.COMPLETED
        self._append("COUNTERSIGNED", approval)
        return approval

    def withdraw(self, approval_id: str, by: str, reason: str) -> Approval:
        approval = self.items.get(approval_id)
        if approval is None:
            raise DualControlError(f"no approval is open as '{approval_id}'")
        if approval.state != ApprovalState.AWAITING:
            raise DualControlError(f"{approval_id} is {approval.state.lower()}")
        approval.state = ApprovalState.WITHDRAWN
        approval.closed_reason = f"withdrawn by {by}: {reason}".strip()
        self._append("WITHDRAWN", approval)
        return approval

    def open_requests(self, action: str | None = None, subject: str | None = None) -> list[Approval]:
        now = _now()
        out = []
        for approval in self.items.values():
            if approval.state != ApprovalState.AWAITING or approval.expired(now):
                continue
            if action and approval.action != action:
                continue
            if subject and approval.subject != subject:
                continue
            out.append(approval)
        return sorted(out, key=lambda a: a.first_at)

    def countersignature(self, approval: Approval) -> Countersignature:
        """The completed approval expressed as the second half the authority layer requires."""
        if approval.state != ApprovalState.COMPLETED:
            raise DualControlError(f"{approval.approval_id} has not been countersigned")
        return Countersignature(identity=approval.second_by, kind="human",
                                roles=frozenset({approval.second_role}),
                                signature=approval.second_signature,
                                signed_at=approval.second_at,
                                approval_id=approval.approval_id)

    def _append(self, event: str, approval: Approval) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": event,
                                 "recorded_at": _stamp(_now()),
                                 **approval.as_dict()}) + "\n")


STORE = ApprovalStore()
