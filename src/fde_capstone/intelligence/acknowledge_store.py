"""In-memory HITL acknowledgements for exception intelligence (POC 2).

Acknowledging an alert records that a human saw it. It does **not** close a
QMS deviation, release a batch, merge identity, or change journey state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_ACKS: dict[str, dict[str, Any]] = {}


def reset() -> None:
    """Test helper. Production demo process memory is the store."""
    _ACKS.clear()


def acknowledge(
    exception_id: str,
    actor: str,
    note: str | None = None,
) -> dict[str, Any]:
    record = {
        "exception_id": exception_id,
        "acknowledged": True,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "acknowledged_by": actor or "unspecified-operator",
        "acknowledgement_note": note or "",
        "effect_on_systems_of_record": "none",
        "authority_requirement": "human-qa-or-coi",
    }
    _ACKS[exception_id] = record
    return record


def get(exception_id: str) -> dict[str, Any] | None:
    return _ACKS.get(exception_id)


def overlay(exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach HITL acknowledgement metadata without mutating detector output."""
    out = []
    for row in exceptions:
        item = dict(row)
        ack = _ACKS.get(item["exception_id"])
        if ack:
            item["acknowledged"] = True
            item["acknowledged_at"] = ack["acknowledged_at"]
            item["acknowledged_by"] = ack["acknowledged_by"]
            item["acknowledgement_note"] = ack["acknowledgement_note"]
        else:
            item["acknowledged"] = False
            item["acknowledged_at"] = None
            item["acknowledged_by"] = None
            item["acknowledgement_note"] = None
        out.append(item)
    return out
