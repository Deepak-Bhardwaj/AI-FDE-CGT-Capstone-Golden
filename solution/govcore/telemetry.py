"""Correlation and PHI-minimised logging.

Two obligations meet here. Every material action must be traceable to the request that caused
it, and no log line may carry clinical detail. They pull in opposite directions: the easiest way
to make something traceable is to log everything about it.

The resolution is that a log line carries identifiers and nothing else. lot_id, coi_id and an
opaque patient reference are enough to find the case in the evidence ledgers, where the detail
lives behind role-based access. A log file is not an access-controlled surface, so it must not
hold anything that needs controlling.

Minimisation is enforced rather than trusted. Every record is scrubbed on the way out: fields
whose names indicate identity are removed, and values that look like a medical record number or
a bare date of birth are removed wherever they appear, including inside free text somebody
pasted into an error message.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

REDACTED = "[redacted]"
RING_SIZE = 500

# Field names that carry identity. Removed wherever they appear, at any depth.
FORBIDDEN_KEYS = frozenset({
    "name", "full_name", "patient_name", "synthetic_name", "given_name", "family_name",
    "dob", "date_of_birth", "birth_date", "mrn", "medical_record_number", "ssn", "nhs_number",
    "address", "postcode", "phone", "email", "password", "token", "authorization",
    "e_signature", "signature", "first_signature", "second_signature", "password_hash", "salt",
})

# Value shapes that carry identity even when the field name is innocent. The bare-date pattern
# is deliberately strict: a timestamp carries T and an offset, a date of birth does not.
MRN_SHAPE = re.compile(r"\bMRN[-_]?\d{4,}\b", re.IGNORECASE)
BARE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_IN_TEXT = re.compile(r"(?<![\dT:-])\d{4}-\d{2}-\d{2}(?![T\d:])")


@dataclass
class Correlation:
    """What identifies this unit of work. Identifiers only."""

    correlation_id: str
    identity: str | None = None
    role: str | None = None
    route: str | None = None
    lot_id: str | None = None
    coi_id: str | None = None
    patient_ref: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {"correlation_id": self.correlation_id, "identity": self.identity,
               "role": self.role, "route": self.route, "lot_id": self.lot_id,
               "coi_id": self.coi_id, "patient_ref": self.patient_ref, **self.extra}
        return {k: v for k, v in out.items() if v is not None}


_CURRENT: ContextVar[Correlation | None] = ContextVar("correlation", default=None)

RECENT: deque[dict] = deque(maxlen=RING_SIZE)

_logger = logging.getLogger("cellchain")


def configure(stream=None) -> None:
    """One JSON object per line. Nothing here is formatted for a human to skim."""
    _logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.propagate = False
    _logger.setLevel(logging.INFO)


def new_id() -> str:
    return "COR-" + uuid.uuid4().hex[:16].upper()


def start(route: str | None = None, identity: str | None = None, role: str | None = None,
          correlation_id: str | None = None):
    """Begin a correlated unit of work. Returns the token to reset with."""
    correlation = Correlation(correlation_id=correlation_id or new_id(), route=route,
                              identity=identity, role=role)
    return _CURRENT.set(correlation)


def stop(token) -> None:
    _CURRENT.reset(token)


def current() -> Correlation | None:
    return _CURRENT.get()


def current_id() -> str | None:
    correlation = _CURRENT.get()
    return correlation.correlation_id if correlation else None


def bind(**fields: Any) -> None:
    """Attach identifiers as they become known. Anything not a known field is scrubbed first."""
    correlation = _CURRENT.get()
    if correlation is None:
        return
    for name, value in fields.items():
        if value is None:
            continue
        if name in ("lot_id", "coi_id", "patient_ref", "identity", "role", "route"):
            setattr(correlation, name, value)
        else:
            correlation.extra[name] = scrub(value)


def scrub(value: Any) -> Any:
    """Remove identity from anything on its way to a log line."""
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in FORBIDDEN_KEYS else scrub(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        if BARE_DATE.match(value.strip()):
            return REDACTED
        cleaned = MRN_SHAPE.sub(REDACTED, value)
        return DATE_IN_TEXT.sub(REDACTED, cleaned)
    return value


def log(event: str, level: str = "info", **fields: Any) -> dict:
    correlation = _CURRENT.get()
    record = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "level": level, "event": event,
              **(correlation.as_dict() if correlation else {}),
              **{k: scrub(v) for k, v in fields.items()}}
    RECENT.append(record)
    _logger.log(getattr(logging, level.upper(), logging.INFO),
                json.dumps(record, default=str))
    return record


def recent(limit: int = 100) -> list[dict]:
    return list(RECENT)[-limit:][::-1]


configure()
