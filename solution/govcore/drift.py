"""Rule-version drift detection.

Every audit record this system writes names the rule that decided it and the version of
that rule - ``R-QA-RELEASE v2.1``. Nothing, until now, tied that version to the code that
actually implements it. A gate's logic could be changed while its version string stayed
put, and every record written afterwards would claim a lineage it no longer had. Records
that misstate their own provenance are worse than records with none, because they are
believed.

This module seals each rule's implementation to a fingerprint and reports when the two
have parted company. The safety KPI measurements and the accountability model are sealed
alongside them, because a number that proves the system is safe, and a map that says who
may approve, are only worth the assurance that they still work the way they did when
someone approved them.

    MATCHED    the code is the code that was sealed under this version
    DRIFTED    the code changed and the version did not - the defect this exists to catch
    REVISED    the version changed, so the seal is stale and a human must renew it
    UNSEALED   an implemented rule nobody has sealed
    ORPHANED   a seal for a rule that no longer exists
    UNREADABLE source unavailable, so no assurance can be offered either way

Sealing is a repository act, performed by a person through ``python -m govcore.drift
--seal``, and never an API call. A running service that could re-seal itself could erase
the evidence of its own drift, which would make this control decorative.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import accountability, gates, kpi, release_gate

BASELINE_PATH = Path(__file__).with_name("rule_baseline.json")
FINGERPRINT_VERSION = "drift/1.0"

MATCHED = "MATCHED"
DRIFTED = "DRIFTED"
REVISED = "REVISED"
UNSEALED = "UNSEALED"
ORPHANED = "ORPHANED"
UNREADABLE = "UNREADABLE"

#: Statuses that mean the control is not satisfied.
FAILING = (DRIFTED, REVISED, UNSEALED, ORPHANED, UNREADABLE)


@dataclass(frozen=True)
class Subject:
    """One rule, and the function that decides it."""
    key: str
    rule_id: str
    rule_version: str
    statement: str
    source_system: str
    fn: Callable
    #: Values the function reads but does not contain. A threshold declared elsewhere is
    #: still part of the rule, and changing it changes the rule.
    constants: tuple[tuple[str, str], ...] = ()


def subjects() -> list[Subject]:
    """Every rule, measurement and authority definition under change control."""
    out: list[Subject] = []
    for fn in gates.GATES:
        gate_id = _gate_id_of(fn)
        rule = gates.RULES.get(gate_id, gates.UNREGISTERED_RULE)
        out.append(Subject(gate_id, rule["rule_id"], rule["rule_version"],
                           rule["statement"], rule["source_system"], fn))
    out.append(Subject("RELEASE", release_gate.RULE_ID, release_gate.RULE_VERSION,
                       "Release derives solely from a recorded QMS disposition, gated on QC "
                       "evidence, deviation disposition and a qualified signature.",
                       "QMS", release_gate.evaluate_release))
    for key, spec in kpi.SEALED.items():
        out.append(Subject(key, key, kpi.MEASURE_VERSION, spec["statement"],
                           "Safety KPI measurement", spec["fn"],
                           tuple(sorted((k, repr(v))
                                        for k, v in spec.get("constants", {}).items()))))
    for key, spec in accountability.SEALED.items():
        out.append(Subject(key, key, accountability.MODEL_VERSION, spec["statement"],
                           "Accountability model", spec["fn"],
                           tuple(sorted((k, repr(v))
                                        for k, v in spec.get("constants", {}).items()))))
    return out


def _gate_id_of(fn: Callable) -> str:
    """``_gate8_qms_release`` -> ``G8``. The registry is keyed by gate id, the tuple is not."""
    digits = ""
    for ch in fn.__name__.removeprefix("_gate"):
        if not ch.isdigit():
            break
        digits += ch
    return f"G{digits}" if digits else fn.__name__


def normalise(source: str) -> str:
    """Strip only what cannot change meaning: indentation, trailing space, blank lines.

    Comments are kept deliberately. This module cannot tell a comment that restates the
    code from one that states the rule the code is meant to implement, and guessing wrong
    in the permissive direction is how a rule change slips through as a formatting change.
    Re-sealing costs a person one command; missing a drift costs an audit.
    """
    lines = [ln.rstrip() for ln in textwrap.dedent(source).splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


def fingerprint(subject: Subject) -> str | None:
    """A hash over the implementation and the rule text a reviewer would be shown.

    Both are included because either changing alone is a change of rule: new code under an
    old sentence misleads, and a new sentence over old code misleads harder.
    """
    try:
        source = inspect.getsource(subject.fn)
    except (OSError, TypeError):
        return None
    material = "\n".join([FINGERPRINT_VERSION, subject.rule_id, subject.statement,
                          subject.source_system, normalise(source),
                          *(f"{k}={v}" for k, v in subject.constants)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _v(version: str | None) -> str:
    """Two versioning schemes live here: bare ``2.1`` and namespaced ``release-gate/2.0.0``."""
    if not version:
        return "an unrecorded version"
    return version if "/" in version else f"v{version}"


def load_baseline(path: Path | None = None) -> dict:
    p = path or BASELINE_PATH
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("seals", {})
    except (json.JSONDecodeError, OSError):
        return {}


@dataclass(frozen=True)
class Finding:
    key: str
    rule_id: str
    status: str
    detail: str
    sealed_version: str | None = None
    current_version: str | None = None
    sealed_by: str | None = None
    sealed_at: str | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == MATCHED

    def as_dict(self) -> dict:
        return {"key": self.key, "rule_id": self.rule_id, "status": self.status,
                "detail": self.detail, "sealed_version": self.sealed_version,
                "current_version": self.current_version, "sealed_by": self.sealed_by,
                "sealed_at": self.sealed_at, "seal_reason": self.reason}


def scan(subject_list: list[Subject] | None = None, baseline: dict | None = None) -> list[Finding]:
    """Compare every implemented rule with its seal, and every seal with its rule."""
    subs = subjects() if subject_list is None else subject_list
    seals = load_baseline() if baseline is None else baseline
    findings: list[Finding] = []
    seen: set[str] = set()

    for s in subs:
        seen.add(s.key)
        seal = seals.get(s.key)
        current = fingerprint(s)
        if current is None:
            findings.append(Finding(
                s.key, s.rule_id, UNREADABLE,
                "The source of this rule could not be read, so no statement can be made "
                "about whether it matches what was sealed.",
                (seal or {}).get("rule_version"), s.rule_version))
            continue
        if seal is None:
            findings.append(Finding(
                s.key, s.rule_id, UNSEALED,
                f"{s.rule_id} {_v(s.rule_version)} is implemented but has never been sealed, "
                f"so records naming this version assert a lineage nobody has checked.",
                None, s.rule_version))
            continue
        if seal.get("fingerprint") == current and seal.get("rule_version") == s.rule_version:
            findings.append(Finding(
                s.key, s.rule_id, MATCHED,
                f"Implementation matches the seal for {s.rule_id} {_v(s.rule_version)}.",
                seal.get("rule_version"), s.rule_version, seal.get("sealed_by"),
                seal.get("sealed_at"), seal.get("reason")))
        elif seal.get("rule_version") != s.rule_version:
            findings.append(Finding(
                s.key, s.rule_id, REVISED,
                f"{s.rule_id} moved from {_v(seal.get('rule_version'))} to "
                f"{_v(s.rule_version)}. The version bump was declared; the seal has not been "
                f"renewed, so nothing yet records who approved the change or why.",
                seal.get("rule_version"), s.rule_version, seal.get("sealed_by"),
                seal.get("sealed_at"), seal.get("reason")))
        else:
            findings.append(Finding(
                s.key, s.rule_id, DRIFTED,
                f"The implementation of {s.rule_id} changed while its version stayed at "
                f"{_v(s.rule_version)}. Every decision recorded since cites a version that no "
                f"longer describes the code that made it.",
                seal.get("rule_version"), s.rule_version, seal.get("sealed_by"),
                seal.get("sealed_at"), seal.get("reason")))

    for key, seal in seals.items():
        if key not in seen:
            findings.append(Finding(
                key, seal.get("rule_id", "unknown"), ORPHANED,
                "A seal exists for a rule this build does not implement. Either the rule was "
                "removed without withdrawing its seal, or it was renamed and its history lost.",
                seal.get("rule_version"), None, seal.get("sealed_by"), seal.get("sealed_at"),
                seal.get("reason")))

    return sorted(findings, key=lambda f: (f.status == MATCHED, f.key))


def status(**kwargs) -> dict:
    findings = scan(**kwargs)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    failing = [f for f in findings if not f.ok]
    return {
        "control": "rule and measurement drift",
        "fingerprint_version": FINGERPRINT_VERSION,
        "checked": len(findings),
        "intact": not failing,
        "counts": counts,
        "findings": [f.as_dict() for f in findings],
        "meaning": ("Every rule and measurement matches the version it claims."
                    if not failing else
                    f"{len(failing)} rule(s) do not match their seal. Decisions recorded "
                    f"under the affected versions cite a lineage that cannot be confirmed."),
        "sealing": "Sealing is a repository act (python -m govcore.drift --seal), never an "
                   "API call. A service that could re-seal itself could hide its own drift.",
    }


def seal(sealed_by: str, reason: str, path: Path | None = None) -> dict:
    """Record the current implementations as approved. Deliberately not exposed over HTTP."""
    if not sealed_by.strip():
        raise ValueError("A seal must name the person who approved the change.")
    if len(reason.strip()) < 10:
        raise ValueError("A seal must say why the rule changed, in a sentence a reviewer "
                         "can read.")
    p = path or BASELINE_PATH
    existing = load_baseline(p)
    now = datetime.now(timezone.utc).isoformat()
    seals: dict[str, dict] = {}
    for s in subjects():
        fp = fingerprint(s)
        if fp is None:
            raise RuntimeError(f"Cannot seal {s.key}: its source could not be read.")
        prior = existing.get(s.key)
        unchanged = prior and prior.get("fingerprint") == fp and \
            prior.get("rule_version") == s.rule_version
        seals[s.key] = dict(prior) if unchanged else {
            "rule_id": s.rule_id, "rule_version": s.rule_version, "fingerprint": fp,
            "sealed_by": sealed_by.strip(), "sealed_at": now, "reason": reason.strip(),
        }
    document = {"fingerprint_version": FINGERPRINT_VERSION,
                "policy_version": gates.POLICY_VERSION,
                "note": "Generated by govcore.drift. Each seal binds a rule version to the "
                        "code that implements it. Renew a seal only when the change it "
                        "covers has been approved.",
                "seals": seals}
    p.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def _main(argv: list[str]) -> int:
    if "--seal" in argv:
        rest = [a for a in argv if a != "--seal"]
        by = rest[0] if rest else input("Sealed by (identity): ").strip()
        why = rest[1] if len(rest) > 1 else input("Reason for the change: ").strip()
        doc = seal(by, why)
        print(f"Sealed {len(doc['seals'])} rules as {by}.")
        return 0
    report = status()
    for f in report["findings"]:
        mark = " ok " if f["status"] == MATCHED else "DRIFT" if f["status"] == DRIFTED else "----"
        print(f"[{mark}] {f['key']:<8} {f['rule_id']:<24} {f['status']}")
        if f["status"] != MATCHED:
            print(f"         {f['detail']}")
    print(f"\n{report['meaning']}")
    return 0 if report["intact"] else 1


if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(_main(sys.argv[1:]))
