"""Agent registry and bounded invocation.

Every agent is declared with a full tool contract (capability stack section 8.3) and every
invocation returns evidence, confidence, uncertainty, required authority, model and prompt
version, and audit metadata. Agents are deterministic in this build - no LLM is configured -
so the control plane behaves identically whether or not a model is available.

No agent is registered for any Class D action. The absence is the control.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import gates, identity, intelligence, ratelimit, timeline
from .loader import Estate, load, parse_time
from .types import ActionClass, Evidence, Trust

PROMPT_VERSION = "prompts/2026.3.0"
MODEL_NAME = "deterministic-baseline"     # swapped for an LLM adapter only behind a feature flag
MODEL_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ToolContract:
    allowed_callers: frozenset[str]
    input_schema: str
    data_classification: str
    access: str                 # "read" | "read-write"
    side_effects: str
    approval_required: str
    idempotency: str
    rate_limit: str
    logging: str
    failure_behaviour: str

    def as_dict(self) -> dict:
        return {
            "allowed_callers": sorted(self.allowed_callers),
            "input_schema": self.input_schema,
            "data_classification": self.data_classification,
            "access": self.access, "side_effects": self.side_effects,
            "approval_required": self.approval_required, "idempotency": self.idempotency,
            "rate_limit": self.rate_limit, "logging": self.logging,
            "failure_behaviour": self.failure_behaviour,
        }


@dataclass
class AgentResult:
    agent_id: str
    action: str
    action_class: ActionClass
    summary: str
    findings: list[dict] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty: str = ""
    required_authority: str = ""
    auto_apply: bool = False
    model_name: str = MODEL_NAME
    model_version: str = MODEL_VERSION
    prompt_version: str = PROMPT_VERSION
    invoked_at: str = field(default_factory=_now)
    subject: str = ""

    def as_dict(self) -> dict:
        return {
            "agent_id": self.agent_id, "action": self.action,
            "action_class": self.action_class.value, "summary": self.summary,
            "findings": self.findings, "evidence": [e.as_dict() for e in self.evidence],
            "confidence": round(self.confidence, 3), "uncertainty": self.uncertainty,
            "required_authority": self.required_authority, "auto_apply": self.auto_apply,
            "model": {"name": self.model_name, "version": self.model_version,
                      "prompt_version": self.prompt_version},
            "invoked_at": self.invoked_at, "subject": self.subject,
        }


@dataclass(frozen=True)
class Agent:
    agent_id: str
    name: str
    purpose: str
    action: str
    action_class: ActionClass
    authority: str
    prohibited: tuple[str, ...]
    contract: ToolContract
    run: Callable[..., AgentResult]

    def as_dict(self) -> dict:
        return {
            "agent_id": self.agent_id, "name": self.name, "purpose": self.purpose,
            "action": self.action, "action_class": self.action_class.value,
            "authority": self.authority, "prohibited": list(self.prohibited),
            "contract": self.contract.as_dict(),
        }


ACTIVITY: list[dict] = []


def _record(result: AgentResult) -> AgentResult:
    ACTIVITY.append(result.as_dict())
    return result


def activity(limit: int = 40) -> list[dict]:
    return ACTIVITY[-limit:][::-1]


# --------------------------------------------------------------------------- #
# Agent implementations
# --------------------------------------------------------------------------- #

def _explain_readiness(subject: str, estate: Estate | None = None, **_) -> AgentResult:
    """Grounded explanation of a gate result. Cannot change the result."""
    est = estate or load()
    assessment = gates.evaluate(subject, est)
    blocking = [g for g in assessment.gates
                if g.status in (gates.GateStatus.FAIL, gates.GateStatus.CONFLICT)]
    unknown = [g for g in assessment.gates if g.status is gates.GateStatus.UNKNOWN]

    findings = [{
        "gate": g.gate_id, "name": g.name, "status": g.status.value,
        "explanation": g.reason, "authority": g.authority, "sop": g.sop_ref,
    } for g in blocking + unknown]

    ev = [Evidence("GATE_ENGINE", g.gate_id, g.status.value, ", ".join(g.evidence_refs))
          for g in blocking + unknown]

    if blocking:
        summary = (f"{subject} is {assessment.readiness.value.lower()}. {len(blocking)} check(s) "
                   f"are failing or contradictory, and {assessment.required_authority} must act.")
    elif unknown:
        summary = (f"{subject} needs more evidence. Nothing has failed, but {len(unknown)} "
                   "check(s) have no evidence yet, and missing evidence is not a pass.")
    else:
        summary = (f"{subject} satisfies every applicable check under policy "
                   f"{assessment.policy_version}.")

    return _record(AgentResult(
        "AG-EXPLAIN", "explain_readiness", ActionClass.B_ADVISORY, summary, findings, ev,
        confidence=assessment.confidence,
        uncertainty="Explanation restates deterministic gate results; it cannot alter them.",
        required_authority=assessment.required_authority, subject=subject))


def _identity_candidates(subject: str, estate: Estate | None = None, **_) -> AgentResult:
    est = estate or load()
    a = identity.assess(subject, est)
    findings = [{"conflict": c, "interpretation": _interpret_conflict(c)} for c in a.conflicts]
    summary = (f"{subject}: {a.outcome.value}. " +
               ("Safety-critical identifier conflict - automatic linkage refused."
                if a.blocking else "Identifiers corroborate across sources."))
    return _record(AgentResult(
        "AG-IDENTITY", "propose_identity_link", ActionClass.B_ADVISORY, summary, findings,
        a.evidence, confidence=a.confidence,
        uncertainty=("A conflicting date of birth or MRN can never be auto-merged regardless of "
                     "score. There is no threshold high enough."),
        required_authority="Identity adjudicator", subject=subject))


def _interpret_conflict(conflict: str) -> str:
    """Pattern explanation, not a correction."""
    if conflict.startswith("dob:"):
        return ("Dates differ by a single day across the whole population, which indicates a "
                "timezone truncation in one export rather than a data-entry error.")
    if conflict.startswith("mrn:") and "MRN0" in conflict:
        return ("Digits are identical; a hyphen has become a zero. This is delimiter drift at the "
                "export boundary, not two different patients.")
    if conflict.startswith("center_id:"):
        return "Centres differ genuinely, including across countries. Requires human adjudication."
    return "Requires human adjudication."


def _triage_exceptions(subject: str = "", estate: Estate | None = None, limit: int = 10, **_) -> AgentResult:
    est = estate or load()
    ranked = intelligence.rank_exceptions(est, limit=limit)
    findings = [r.as_dict() for r in ranked]
    ev = [Evidence("EXCEPTION_REGISTER", r.exception_id, r.score, "deviations.csv") for r in ranked]
    summary = (f"{len(ranked)} exceptions ranked by patient impact and time-criticality. "
               f"Highest: {ranked[0].exception_id} ({ranked[0].kind}) at score {round(ranked[0].score,1)}."
               if ranked else "No open exceptions.")
    return _record(AgentResult(
        "AG-TRIAGE", "rank_exceptions", ActionClass.B_ADVISORY, summary, findings, ev,
        confidence=0.7,
        uncertainty=("Ranking reorders a worklist only. It cannot close, assign or disposition. "
                     "The impact model requires clinical review before it is trusted for triage."),
        required_authority="Operations", subject=subject or "population"))


def _forecast_release(subject: str, estate: Estate | None = None, **_) -> AgentResult:
    """Calibrated interval, never a point estimate."""
    est = estate or load()
    batches = est.batches_by_key.get(subject, [])
    if not batches:
        return _record(AgentResult(
            "AG-FORECAST", "forecast_release", ActionClass.B_ADVISORY,
            f"{subject} has no manufacturing batch; no forecast is possible.", [], [],
            0.0, "No batch exists. Abstaining rather than guessing.",
            "Manufacturing planner", subject=subject))

    batch = batches[0]
    lags = []
    for row in est.qc:
        sampled, reported = parse_time(row["sampled_at"]), parse_time(row["reported_at"])
        if sampled and reported:
            lags.append((reported - sampled).total_seconds() / 3600)

    mean = statistics.mean(lags)
    p10, p90 = statistics.quantiles(lags, n=10)[0], statistics.quantiles(lags, n=10)[-1]
    anchor = parse_time(batch["mfg_end"])
    assessment = gates.evaluate(subject, est)
    open_gates = [g.gate_id for g in assessment.gates
                  if g.status in (gates.GateStatus.FAIL, gates.GateStatus.CONFLICT)]

    findings = [{
        "batch_id": batch["batch_id"],
        "qc_latency_mean_h": round(mean, 1),
        "interval_80pct_h": [round(p10, 1), round(p90, 1)],
        "earliest": (anchor + timedelta(hours=p10)).isoformat() if anchor else None,
        "latest": (anchor + timedelta(hours=p90)).isoformat() if anchor else None,
        "open_gates": open_gates,
    }]
    summary = (f"QA release for {batch['batch_id']} is 80% likely between "
               f"{round(p10,1)}h and {round(p90,1)}h after manufacturing end "
               f"(mean QC latency {round(mean,1)}h).")
    if open_gates:
        summary += f" Forecast is conditional: gates {', '.join(open_gates)} are not satisfied."

    return _record(AgentResult(
        "AG-FORECAST", "forecast_release", ActionClass.B_ADVISORY, summary, findings,
        [Evidence("LIMS", "qc.latency_distribution", f"n={len(lags)}", "qc_results.csv")],
        confidence=0.55,
        uncertainty=("Interval, not a point estimate. Conditioning chemotherapy must never be "
                     "scheduled against the lower bound. Calibration degrades under regime change."),
        required_authority="Manufacturing planner (not Quality)", subject=subject))


def _forecast_journey(subject: str, estate: Estate | None = None, **_) -> AgentResult:
    """Whole-journey timing: recorded actuals, cohort expectations, intervals for what remains.

    A subject of PROSPECTIVE:<date> asks the same question for a patient not yet enrolled.
    """
    est = estate or load()

    if subject.upper().startswith("PROSPECTIVE:"):
        start = parse_time(subject.partition(":")[2])
        if start is None:
            return _record(AgentResult(
                "AG-JOURNEY", "forecast_journey", ActionClass.B_ADVISORY,
                "That enrolment date could not be read.", [], [], 0.0,
                "Abstaining rather than guessing a start date.", "Operations", subject=subject))
        projection = timeline.project_new(start, est)
        window = projection["ready_window"]
        return _record(AgentResult(
            "AG-JOURNEY", "forecast_journey", ActionClass.B_ADVISORY,
            (f"A patient enrolling on {start.date()} would, on this estate's own history, reach "
             f"QA release around {window['expected'][:10]} — about "
             f"{projection['expected_total_days']} days — with a plausible range of "
             f"{window['earliest'][:10]} to {window['latest'][:10]}."),
            [projection],
            [Evidence("cohort", "transition.quantiles", timeline.MODEL["method"], "events.jsonl")],
            confidence=0.35,
            uncertainty=("Nothing is known about this patient yet, so this is the cohort's shape "
                         "rolled forward: no capacity check, no clinical assessment, no payer "
                         "decision. Treat it as a planning aid only and never quote it as a date "
                         "to a patient."),
            required_authority="Operations (advisory; no scheduling authority)", subject=subject))

    projection = timeline.forecast(subject, est)
    if not projection["enrolled_at"]:
        return _record(AgentResult(
            "AG-JOURNEY", "forecast_journey", ActionClass.B_ADVISORY,
            f"{subject} has no enrolment event, so there is nothing to measure from.", [], [],
            0.0, "Abstaining rather than anchoring a timeline on an assumed start date.",
            "Operations", subject=subject))

    assessment = gates.evaluate(subject, est)
    open_gates = [g.gate_id for g in assessment.gates
                  if g.status in (gates.GateStatus.FAIL, gates.GateStatus.CONFLICT,
                                  gates.GateStatus.UNKNOWN)]
    done = projection["completed_milestones"]
    final = projection["predicted_completion"]

    if projection["already_complete"]:
        summary = (f"The QMS records {subject} as released by Quality; the timeline below is what "
                   "actually happened.")
    elif final:
        summary = (f"{done} of {projection['total_milestones']} milestones are recorded. On this "
                   f"estate's own transition times, {projection['predicted_completion_label'].lower()} "
                   f"falls between {final['earliest'][:10]} and {final['latest'][:10]}, most likely "
                   f"around {final['expected'][:10]}. The infusion date itself is set by the "
                   "treating clinician after release and is not estimated here.")
    else:
        summary = (f"{done} of {projection['total_milestones']} milestones are recorded. There is "
                   "not enough comparable history to project the remaining steps.")
    if open_gates:
        summary += (f" This assumes checks {', '.join(open_gates)} are cleared first; while they "
                    "are open the dates are not achievable."
                    if not projection["already_complete"] else
                    f" Checks {', '.join(open_gates)} are nonetheless still open, so the QMS record "
                    "and the governed verdict disagree.")

    return _record(AgentResult(
        "AG-JOURNEY", "forecast_journey", ActionClass.B_ADVISORY, summary, [projection],
        [Evidence("event log", "journey.milestones", projection["completed_milestones"],
                  "events.jsonl"),
         Evidence("cohort", "transition.quantiles", timeline.MODEL["method"], "events.jsonl")],
        confidence=projection["confidence"],
        uncertainty=("Intervals from this estate's own history, not a commitment. They ignore "
                     "clinical fitness, capacity and any open check. Conditioning chemotherapy "
                     "must never be scheduled from these dates - only a treating clinician "
                     "schedules conditioning, against confirmed release."),
        required_authority="Operations (advisory; no scheduling authority)", subject=subject))


def _propose_route(subject: str, estate: Estate | None = None, **_) -> AgentResult:
    est = estate or load()
    shipments = est.shipments_by_key.get(subject, [])
    findings, ev = [], []
    for ship in shipments:
        courier = est.courier_by_id.get(ship["courier_id"], {})
        dep, arr = parse_time(ship["departed_at"]), parse_time(ship["arrived_at"])
        transit = round((arr - dep).total_seconds() / 3600, 1) if dep and arr and arr >= dep else None
        sla = float(courier.get("sla_hours", 0) or 0)
        findings.append({
            "shipment_id": ship["shipment_id"], "direction": ship["direction"],
            "courier": courier.get("name"), "sla_hours": sla, "transit_hours": transit,
            "sla_breach": bool(transit and sla and transit > sla),
            "alternatives": [c["name"] for c in est.couriers
                             if c["courier_id"] != ship["courier_id"]][:2],
        })
        ev.append(Evidence("LOGISTICS", "shipment.transit", transit, ship["shipment_id"]))

    breaches = sum(1 for f in findings if f["sla_breach"])
    summary = (f"{len(findings)} shipment(s) reviewed; {breaches} exceeded the contracted SLA. "
               "Alternative carriers are proposals only.")
    return _record(AgentResult(
        "AG-ROUTE", "propose_route", ActionClass.B_ADVISORY, summary, findings, ev,
        confidence=0.6,
        uncertainty=("Carrier suitability for cryogenic lanes and jurisdictions is not modelled. "
                     "Logistics must validate any alternative."),
        required_authority="Logistics coordinator", subject=subject))


def _extract_document(subject: str, document: dict | None = None, **_) -> AgentResult:
    doc = document or {}
    result = intelligence.extract_from_document(doc)
    findings = [dict(p) for p in result.proposals]
    if result.injection_detected:
        findings.append({
            "kind": "SECURITY_SIGNAL",
            "detail": f"instruction-like patterns matched: {len(result.injection_matches)}",
            "effect": "none - content is data and the extractor holds no tools",
        })
    summary = (f"{len(result.proposals)} proposal(s) extracted from untrusted content. "
               "Nothing is applied automatically.")
    return _record(AgentResult(
        "AG-EXTRACT", "extract_from_document", ActionClass.B_ADVISORY, summary, findings,
        [Evidence("DOCUMENT", "content", doc.get("file", "upload"), doc.get("file", "upload"),
                  trust=Trust.UNTRUSTED)],
        confidence=0.5,
        uncertainty=("Extraction is lossy and the source is untrusted. Every proposal requires "
                     "human confirmation before it becomes evidence."),
        required_authority="Depends on proposal kind", subject=subject or doc.get("file", "upload")))


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_READ_ONLY = dict(access="read", side_effects="none", idempotency="pure function of input",
                  logging="mandatory, including refusals", failure_behaviour="fail closed")

REGISTRY: dict[str, Agent] = {
    "AG-EXPLAIN": Agent(
        "AG-EXPLAIN", "Readiness explainer",
        "Explains why a journey is blocked, which evidence conflicts and who must act.",
        "explain_readiness", ActionClass.B_ADVISORY, "Operations",
        ("change a gate result", "declare a journey ready", "infer missing evidence"),
        ToolContract(frozenset({"ops_coordinator", "quality_reviewer", "auditor", "ai_service"}),
                     "{subject: PatientId}", "PSEUDONYMOUS + OPERATIONAL",
                     approval_required="none (advisory)", rate_limit="120/min", **_READ_ONLY),
        _explain_readiness),
    "AG-IDENTITY": Agent(
        "AG-IDENTITY", "Identity candidate generator",
        "Explains why records might or might not describe the same patient.",
        "propose_identity_link", ActionClass.B_ADVISORY, "Identity adjudicator",
        ("merge identities", "change COI", "invent missing linkage", "suppress contradicting evidence"),
        ToolContract(frozenset({"identity_adjudicator", "ai_service"}),
                     "{subject: PatientId}", "PSEUDONYMOUS + OPERATIONAL",
                     approval_required="Identity adjudicator", rate_limit="60/min", **_READ_ONLY),
        _identity_candidates),
    "AG-TRIAGE": Agent(
        "AG-TRIAGE", "Exception triage",
        "Ranks and summarizes open exceptions by patient impact and deadline pressure.",
        "rank_exceptions", ActionClass.B_ADVISORY, "Operations",
        ("close an exception", "assign ownership", "disposition a deviation"),
        ToolContract(frozenset({"ops_coordinator", "auditor", "ai_service"}),
                     "{limit: int}", "PSEUDONYMOUS + OPERATIONAL",
                     approval_required="none (advisory)", rate_limit="60/min", **_READ_ONLY),
        _triage_exceptions),
    "AG-FORECAST": Agent(
        "AG-FORECAST", "QA release forecaster",
        "Predicts a calibrated release interval and explains its drivers.",
        "forecast_release", ActionClass.B_ADVISORY, "Manufacturing planner (not Quality)",
        ("release a batch", "shorten a QC requirement", "issue a point estimate"),
        ToolContract(frozenset({"manufacturing_planner", "ops_coordinator", "ai_service"}),
                     "{subject: PatientId}", "PSEUDONYMOUS + OPERATIONAL",
                     approval_required="none (advisory)", rate_limit="60/min", **_READ_ONLY),
        _forecast_release),
    "AG-JOURNEY": Agent(
        "AG-JOURNEY", "Journey timeline forecaster",
        "Shows what each stage actually took, what the cohort usually takes, and an interval "
        "for the steps that have not happened yet.",
        "forecast_journey", ActionClass.B_ADVISORY, "Operations (advisory; no scheduling authority)",
        ("schedule conditioning", "commit a date to a patient", "issue a point estimate",
         "treat an estimate as an appointment"),
        ToolContract(frozenset({"ops_coordinator", "manufacturing_planner", "logistics_coordinator",
                                "quality_reviewer", "identity_adjudicator", "auditor",
                                "ai_service"}),
                     "{subject: PatientId}", "PSEUDONYMOUS + OPERATIONAL",
                     approval_required="none (advisory)", rate_limit="120/min", **_READ_ONLY),
        _forecast_journey),
    "AG-ROUTE": Agent(
        "AG-ROUTE", "Logistics route advisor",
        "Reviews custody and transit performance and proposes alternative carriers.",
        "propose_route", ActionClass.B_ADVISORY, "Logistics coordinator",
        ("declare material suitable after an excursion", "rebook a carrier", "disposition a shipment"),
        ToolContract(frozenset({"logistics_coordinator", "ops_coordinator", "ai_service"}),
                     "{subject: PatientId}", "PSEUDONYMOUS + OPERATIONAL + LOGISTICS",
                     approval_required="Logistics coordinator", rate_limit="60/min", **_READ_ONLY),
        _propose_route),
    "AG-EXTRACT": Agent(
        "AG-EXTRACT", "Untrusted document extractor",
        "Converts emails, notes and uploaded reports into schema-constrained proposals.",
        "extract_from_document", ActionClass.B_ADVISORY, "Depends on proposal kind",
        ("apply a proposal", "call any other tool", "reach the network", "write to any system"),
        ToolContract(frozenset({"ai_service", "ops_coordinator"}),
                     "{file, subject, body}", "UNTRUSTED",
                     approval_required="human confirmation before use", rate_limit="60/min",
                     **_READ_ONLY),
        _extract_document),
}

# Class D actions with deliberately no agent. Surfaced in the UI so the absence is auditable.
NO_AGENT_BY_DESIGN = (
    ("release_product", "Quality only"),
    ("disposition_excursion", "Quality only"),
    ("merge_identity", "Identity adjudicator"),
    ("adjudicate_registration", "Identity adjudicator"),
    ("correct_coi", "QA COI adjudicator"),
    ("set_clinical_priority", "Named clinical authority"),
    ("schedule_conditioning", "Treating clinician"),
    ("override_consent", "Clinical authority"),
)


class AgentRefused(PermissionError):
    pass


def invoke(agent_id: str, caller_role: str, subject: str = "",
           estate: Estate | None = None, caller: str | None = None, **kwargs) -> AgentResult:
    agent = REGISTRY.get(agent_id)
    if agent is None:
        raise AgentRefused(f"no agent registered as '{agent_id}'")
    if caller_role not in agent.contract.allowed_callers:
        raise AgentRefused(
            f"role '{caller_role}' is not an allowed caller of {agent_id}; "
            f"permitted: {sorted(agent.contract.allowed_callers)}")
    # Keyed to the individual, so one busy caller cannot spend a whole role's allowance.
    ratelimit.LIMITER.check(f"{agent_id}|{caller or caller_role}",
                            ratelimit.parse(agent.contract.rate_limit))
    return agent.run(subject=subject, estate=estate, **kwargs)


def allowance(agent_id: str, caller: str) -> dict:
    agent = REGISTRY[agent_id]
    limit = ratelimit.parse(agent.contract.rate_limit)
    key = f"{agent_id}|{caller}"
    return {"agent_id": agent_id, "enforced": limit is not None,
            **(limit.as_dict() if limit else {"limit": agent.contract.rate_limit}),
            "used": ratelimit.LIMITER.used(key, limit),
            "remaining": max(0, limit.count - ratelimit.LIMITER.used(key, limit)) if limit else None}


def catalogue() -> dict:
    return {
        "agents": [a.as_dict() for a in REGISTRY.values()],
        "no_agent_by_design": [{"action": a, "authority": auth} for a, auth in NO_AGENT_BY_DESIGN],
        "principle": ("AI interprets, explains, retrieves, summarizes, forecasts and proposes. "
                      "Deterministic gates enforce policy. Authorized humans decide."),
        "model": {"name": MODEL_NAME, "version": MODEL_VERSION, "prompt_version": PROMPT_VERSION,
                  "llm_configured": False},
        "rate_limits_enforced": True,
    }
