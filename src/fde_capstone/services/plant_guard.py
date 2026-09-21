"""Plant-connection guard.

The engagement's hard constraint is that nothing may write to a real plant system until
Stages 12, 15, 16 and 18 have *bound* evidence. Held as prose that constraint is a wish. Held
here it is a precondition: no write adapter can register, and no external write can proceed,
unless a signed manifest names each stage and every artefact it cites still hashes to what was
signed.

The default is refusal. An absent manifest is not an ambiguity to resolve in favour of the
caller - it is the answer.

Nothing in this service writes to an external system today. This module exists so that the
first attempt to add one has to pass through a gate rather than a code review.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

SOLUTION = Path(__file__).resolve().parents[1]
ROOT = SOLUTION.parent
MANIFEST_PATH = SOLUTION / "evidence" / "plant_readiness.json"

# The stages the charter names. Connecting before these are bound is the thing being prevented.
REQUIRED_STAGES: dict[str, str] = {
    "S12": "Design Evaluation, Safety & Audit",
    "S15": "Enforce HITL, Identity & Exception Paths",
    "S16": "Instrument Evals, Tests & Observability",
    "S18": "Harden for Production & Validation",
}


class PlantConnectionRefused(PermissionError):
    """Raised when something would write to an external system without bound evidence."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def manifest_hash(manifest: dict) -> str:
    """Commits to the evidence and to both approvers, so neither can be edited after signing."""
    body = {
        "manifest_id": manifest.get("manifest_id"),
        "stages": manifest.get("stages"),
        "approved_by": manifest.get("approved_by"),
        "countersigned_by": manifest.get("countersigned_by"),
        "issued_at": manifest.get("issued_at"),
        "expires_on": manifest.get("expires_on"),
        "systems": manifest.get("systems"),
    }
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


@dataclass
class StageFinding:
    stage_id: str
    name: str
    bound: bool
    reason: str
    artefacts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"stage_id": self.stage_id, "name": self.name, "bound": self.bound,
                "reason": self.reason, "artefacts": self.artefacts}


@dataclass
class ReadinessReport:
    permitted: bool
    reason: str
    stages: list[StageFinding] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    approved_by: str | None = None
    countersigned_by: str | None = None
    expires_on: str | None = None
    manifest_path: str = str(MANIFEST_PATH)

    def as_dict(self) -> dict:
        return {"permitted": self.permitted, "reason": self.reason,
                "required_stages": REQUIRED_STAGES,
                "stages": [s.as_dict() for s in self.stages],
                "systems": self.systems, "approved_by": self.approved_by,
                "countersigned_by": self.countersigned_by, "expires_on": self.expires_on,
                "manifest": self.manifest_path,
                "note": "No external write is possible until every stage above is bound by a "
                        "signed manifest whose cited artefacts still hash to what was signed."}


def _unbound_report(reason: str, path: Path) -> ReadinessReport:
    stages = [StageFinding(sid, name, False, "no signed manifest binds this stage")
              for sid, name in REQUIRED_STAGES.items()]
    return ReadinessReport(False, reason, stages, manifest_path=str(path))


def evaluate(manifest_path: Path | None = None, root: Path | None = None) -> ReadinessReport:
    """Whether a plant connection is permitted, and for each stage, why or why not."""
    path = Path(manifest_path or MANIFEST_PATH)
    base = Path(root or ROOT)

    if not path.exists():
        return _unbound_report(
            "No plant-readiness manifest exists, so no stage is bound and no external write "
            "is permitted.", path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _unbound_report(f"The manifest could not be read: {exc}.", path)
    if not isinstance(manifest, dict):
        return _unbound_report("The manifest is not an object.", path)

    approved_by = manifest.get("approved_by")
    countersigned_by = manifest.get("countersigned_by")
    expires_on = manifest.get("expires_on")
    systems = list(manifest.get("systems") or [])
    declared = manifest.get("stages") or {}

    findings: list[StageFinding] = []
    for stage_id, name in REQUIRED_STAGES.items():
        entry = declared.get(stage_id)
        if not isinstance(entry, dict):
            findings.append(StageFinding(stage_id, name, False, "the manifest does not name it"))
            continue
        artefacts = entry.get("artefacts") or []
        if not artefacts:
            findings.append(StageFinding(stage_id, name, False, "it cites no evidence"))
            continue
        checked, problems = [], []
        for artefact in artefacts:
            rel = artefact.get("path", "")
            expected = artefact.get("sha256", "")
            target = base / rel
            if not target.exists():
                problems.append(f"{rel} does not exist")
                checked.append({"path": rel, "status": "MISSING"})
                continue
            actual = _sha256(target)
            if actual != expected:
                problems.append(f"{rel} has changed since it was signed")
                checked.append({"path": rel, "status": "ALTERED"})
                continue
            checked.append({"path": rel, "status": "BOUND"})
        if problems:
            findings.append(StageFinding(stage_id, name, False, "; ".join(problems), checked))
        else:
            findings.append(StageFinding(
                stage_id, name, True,
                f"bound by {len(checked)} artefact(s) attested by {entry.get('attested_by', 'an unnamed party')}",
                checked))

    report = ReadinessReport(False, "", findings, systems, approved_by, countersigned_by,
                             expires_on, str(path))

    unbound = [f.stage_id for f in findings if not f.bound]
    if unbound:
        report.reason = f"These stages are not bound: {', '.join(unbound)}."
        return report
    if not approved_by or not countersigned_by:
        report.reason = "A plant connection needs two named approvers; the manifest names fewer."
        return report
    if approved_by == countersigned_by:
        report.reason = f"{approved_by} both approved and countersigned; two people are required."
        return report
    if manifest.get("manifest_hash") != manifest_hash(manifest):
        report.reason = "The manifest has been altered since it was signed."
        return report
    if expires_on:
        try:
            if date.fromisoformat(expires_on) < datetime.now(timezone.utc).date():
                report.reason = f"The manifest expired on {expires_on} and must be re-attested."
                return report
        except ValueError:
            report.reason = f"The expiry date '{expires_on}' is not a date."
            return report
    if not systems:
        report.reason = "The manifest names no system, so it authorises nothing."
        return report

    report.permitted = True
    report.reason = (f"Stages {', '.join(REQUIRED_STAGES)} are bound and attested by "
                     f"{approved_by} and {countersigned_by}.")
    return report


def assert_may_connect(system: str, manifest_path: Path | None = None,
                       root: Path | None = None) -> ReadinessReport:
    """The only sanctioned way to reach an external system. Refuses by default."""
    report = evaluate(manifest_path, root)
    if not report.permitted:
        raise PlantConnectionRefused(
            f"Refusing to connect to '{system}'. {report.reason} "
            "Stages 12, 15, 16 and 18 must have bound evidence before any external write.")
    if system not in report.systems:
        raise PlantConnectionRefused(
            f"Refusing to connect to '{system}'. The manifest authorises only "
            f"{', '.join(report.systems)}.")
    return report


@dataclass(frozen=True)
class WriteAdapter:
    name: str
    system: str
    operations: tuple[str, ...]
    compensating_action: str

    def as_dict(self) -> dict:
        return {"name": self.name, "system": self.system, "operations": list(self.operations),
                "compensating_action": self.compensating_action}


WRITE_ADAPTERS: dict[str, WriteAdapter] = {}


def register_write_adapter(name: str, system: str, operations: tuple[str, ...],
                           compensating_action: str, manifest_path: Path | None = None,
                           root: Path | None = None) -> WriteAdapter:
    """Registration is itself gated, so an adapter cannot exist unenabled and be switched on later."""
    if not compensating_action:
        raise PlantConnectionRefused(
            f"'{name}' declares no compensating action. You cannot roll back a collected bag; "
            "an external write without a compensating path is not permitted.")
    assert_may_connect(system, manifest_path, root)
    adapter = WriteAdapter(name, system, tuple(operations), compensating_action)
    WRITE_ADAPTERS[name] = adapter
    return adapter


def status() -> dict:
    report = evaluate()
    return {**report.as_dict(),
            "write_adapters": [a.as_dict() for a in WRITE_ADAPTERS.values()],
            "external_writes_possible": bool(WRITE_ADAPTERS) and report.permitted}
