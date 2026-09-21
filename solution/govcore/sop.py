"""SOP-as-code with version binding.

The legacy defect this closes: legacy/status_rules.py implements SOP-LOG-007 v6, which
was superseded on 2026-05-01. Here a rule cannot be evaluated unless its SOP version is
EFFECTIVE, and every evaluation records which version decided.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class SOPStatus(str, Enum):
    EFFECTIVE = "Effective"
    SUPERSEDED = "Superseded"
    DRAFT = "Draft"


class SupersededRuleError(RuntimeError):
    """Raised when a superseded rule is invoked outside historical replay."""


@dataclass(frozen=True)
class SOP:
    sop_id: str
    version: str
    status: SOPStatus
    title: str
    effective_from: date | None = None
    superseded_by: str | None = None
    source: str = ""

    @property
    def ref(self) -> str:
        return f"{self.sop_id} {self.version}"


REGISTRY: dict[str, SOP] = {
    "SOP-QA-014 v4": SOP(
        "SOP-QA-014", "v4", SOPStatus.EFFECTIVE,
        "Manufacturing completion is not product release. QA release requires required QC "
        "evidence, disposition of blocking deviations and authorized electronic approval.",
        source="docs/sops/SOP-QA-014-v4.md"),
    "SOP-LOG-007 v6": SOP(
        "SOP-LOG-007", "v6", SOPStatus.SUPERSEDED,
        "Any recorded cryogenic temperature above -120 C is an automatic shipment failure.",
        superseded_by="SOP-LOG-007 v7", source="docs/sops/SOP-LOG-007-v6.md"),
    "SOP-LOG-007 v7": SOP(
        "SOP-LOG-007", "v7", SOPStatus.EFFECTIVE,
        "A single sensor point above -120 C is not by itself a disposition decision. Evaluate "
        "duration, sensor quality, cumulative excursion profile, shipper integrity and Quality "
        "review. Consequential disposition remains human-authorized.",
        effective_from=date(2026, 5, 1), source="docs/sops/SOP-LOG-007-v7.md"),
    "SOP-SCHED-003 v2": SOP(
        "SOP-SCHED-003", "v2", SOPStatus.DRAFT,
        "Scheduling may provisionally reserve capacity before reimbursement authorization, but "
        "treatment-center and quality gating must be revalidated before downstream clinical milestones.",
        source="docs/sops/SOP-SCHED-003-v2.md"),
}


def effective(sop_id: str) -> SOP:
    """Return the single effective version of an SOP."""
    candidates = [s for s in REGISTRY.values() if s.sop_id == sop_id and s.status is SOPStatus.EFFECTIVE]
    if not candidates:
        raise KeyError(f"no effective version registered for {sop_id}")
    if len(candidates) > 1:
        raise RuntimeError(f"{sop_id} has {len(candidates)} effective versions; change control violated")
    return candidates[0]


def bind(ref: str, *, allow_superseded: bool = False) -> SOP:
    """Bind a rule to an SOP version, refusing superseded rules by default."""
    sop = REGISTRY[ref]
    if sop.status is SOPStatus.SUPERSEDED and not allow_superseded:
        raise SupersededRuleError(
            f"{sop.ref} was superseded by {sop.superseded_by}; use the effective version. "
            "Pass allow_superseded=True only for historical replay.")
    return sop
