"""Tamper-evident audit service over ``storage.Database``.

The JSONL hash chain in ``services/audit.py`` is a source-estate ledger. This service is
the operational control-tower log: every record is appended to the SQLite ``audit`` table
with a SHA-256 link to the previous row. A deleted, reordered or edited record fails
``verify()`` at a named position rather than disappearing quietly.
"""

from __future__ import annotations

import json
from typing import Any

from ..model import Principal
from ..storage import Database
from .common import correlation

GENESIS = "GENESIS"


def _row(row: Any) -> dict[str, Any]:
    return {
        "audit_id": row["audit_id"],
        "recorded_at": row["recorded_at"],
        "principal": row["principal"],
        "action": row["action"],
        "scope": row["scope"],
        "outcome": row["outcome"],
        "details": json.loads(row["details_json"]),
        "correlation_id": row["correlation_id"],
        "previous_hash": row["previous_hash"],
        "record_hash": row["record_hash"],
    }


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        principal: Principal | str | None,
        action: str,
        scope: str,
        outcome: str,
        details: dict[str, Any],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one hash-chained audit row. Never updates a previous row."""
        trace = correlation(correlation_id)
        audit_id = self.db.audit(principal, action, scope, outcome, details, trace)
        return self.get(audit_id)

    def get(self, audit_id: int) -> dict[str, Any]:
        row = self.db.connection.execute("SELECT * FROM audit WHERE audit_id=?", (audit_id,)).fetchone()
        if not row:
            raise KeyError(audit_id)
        return _row(row)

    def recent(self, limit: int = 40) -> list[dict[str, Any]]:
        bound = max(1, min(int(limit), 100))
        rows = self.db.connection.execute(
            "SELECT * FROM audit ORDER BY audit_id DESC LIMIT ?",
            (bound,),
        ).fetchall()
        return [_row(row) for row in rows]

    def count(self) -> int:
        row = self.db.connection.execute("SELECT COUNT(*) AS n FROM audit").fetchone()
        return int(row["n"])

    def head(self) -> str:
        row = self.db.connection.execute(
            "SELECT record_hash FROM audit ORDER BY audit_id DESC LIMIT 1"
        ).fetchone()
        return row["record_hash"] if row else GENESIS

    def verify(self) -> dict[str, Any]:
        valid = self.db.verify_audit_chain()
        return {
            "chain_valid": valid,
            "entries": self.count(),
            "head": self.head(),
            "genesis": GENESIS,
            "algorithm": "sha256-canonical-json",
            "note": (
                "Each row commits to the previous record_hash. "
                "An edited outcome, reordered id or missing row fails the chain."
            ),
        }

    def snapshot(self, limit: int = 40) -> dict[str, Any]:
        """Control-tower payload: integrity first, then the recent records."""
        report = self.verify()
        return {**report, "records": self.recent(limit)}
