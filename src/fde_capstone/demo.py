from __future__ import annotations

from pathlib import Path
from typing import Any

from .application import CapstoneApplication
from .model import Outcome, Principal

T0 = "2026-01-01T10:00:00+00:00"

ROLE_VIEWS = [
    {"id":"patient_operations","name":"Patient Operations Coordinator","backend_role":"COORDINATOR","focus":"End-to-end journey, blockers, evidence and accountable next owner.","can_do":["Read the journey","Create owned exception cases","Coordinate the next authorized action"],"cannot_do":["Resolve patient identity","Release product","Make clinical decisions"]},
    {"id":"identity_authority","name":"Identity Authority","backend_role":"IDENTITY_AUTHORITY","focus":"Conflicting patient identity and chain-of-identity evidence.","can_do":["Review cited identity evidence","Apply the reviewed identity decision"],"cannot_do":["Reserve manufacturing capacity","Release product","Make clinical decisions"]},
    {"id":"logistics_planner","name":"Logistics / Manufacturing Planner","backend_role":"PLANNER","focus":"Slot reservation, unknown outcomes, reconciliation and logistics evidence.","can_do":["Reserve a slot","Reconcile an unknown command outcome","Review logistics/thermal evidence"],"cannot_do":["Resolve identity","Release product","Override Quality"]},
    {"id":"manufacturing","name":"Manufacturing Operations","backend_role":"VIEWER","focus":"Batch execution state and upstream/downstream dependencies.","can_do":["Read manufacturing and journey evidence","See blockers and handoffs"],"cannot_do":["Treat MES completion as Quality release","Change identity","Approve clinical actions"]},
    {"id":"lab_qc","name":"Lab / Quality Control","backend_role":"VIEWER","focus":"QC result, deviation and thermal evidence contributing to the Quality packet.","can_do":["Review QC/deviation/thermal evidence","See unresolved Quality prerequisites"],"cannot_do":["Issue the final Quality release in this POC","Change patient identity"]},
    {"id":"quality_authority","name":"Quality Authority","backend_role":"QUALITY_AUTHORITY","focus":"Evidence-backed product disposition and release authority.","can_do":["Review the release evidence packet","Record the authorized release decision"],"cannot_do":["Delegate release authority to AI","Use MES or ERP status as release authority"]},
    {"id":"executive","name":"Executive / Operations Viewer","backend_role":"VIEWER","focus":"Cross-domain status, exceptions, automation controls and evidence traceability.","can_do":["Read the automated cross-domain summary","Inspect control and assurance evidence"],"cannot_do":["Execute operational or consequential decisions"]},
]


def principal(subject: str, role: str, scopes: set[str] | None = None) -> Principal:
    return Principal(subject, frozenset({role}), frozenset(scopes or {"*"}))


def register(app: CapstoneApplication, evidence_id: str, source: str, payload: dict[str, Any]) -> str:
    return app.evidence.register(evidence_id, source, f"synthetic://{evidence_id}", payload, T0, T0)


def run_demo(database_path: str | Path, ai_mode: str = "off") -> dict:
    app = CapstoneApplication(database_path, ai_mode=ai_mode)
    coordinator = principal("demo-coordinator", "COORDINATOR")
    identity_authority = principal("demo-identity-authority", "IDENTITY_AUTHORITY")
    planner = principal("demo-planner", "PLANNER")
    quality_authority = principal("demo-quality-authority", "QUALITY_AUTHORITY")
    viewer = principal("demo-viewer", "VIEWER")
    try:
        identity_evidence: list[tuple[str, str, dict[str, Any]]] = [
            ("EV-ID-MRN","CRM",{"mrn":"MRN-100","patient":"P-A"}),
            ("EV-ID-DOB","CLINICAL",{"dob":"1980-01-01","patient":"P-B"}),
            ("EV-CONSENT","CLINICAL",{"status":"CURRENT"}),
            ("EV-AUTH","PAYER",{"status":"APPROVED"}),
            ("EV-SITE","QMS",{"training":"CURRENT","equipment":"CURRENT"}),
        ]
        for evidence_id, source, payload in identity_evidence:
            register(app,evidence_id,source,payload)

        identity_case=app.identity.detect_conflict(coordinator,"P-A","P-B","MRN/DOB assertions conflict",["EV-ID-MRN","EV-ID-DOB"])
        proposal=app.identity.propose(coordinator,identity_case["case_id"],"P-A","P-B","SAME_SUBJECT",["EV-ID-MRN","EV-ID-DOB"])
        identity_decision=app.identity.decide(identity_authority,identity_case["case_id"],"APPROVE",proposal["proposal_digest"])
        readiness=app.readiness.assess(viewer,"P-A","PRE_COLLECTION",{
            "identity":(Outcome.SATISFIED,["EV-ID-MRN","EV-ID-DOB"]),
            "consent":(Outcome.SATISFIED,["EV-CONSENT"]),
            "authorization":(Outcome.SATISFIED,["EV-AUTH"]),
            "site":(Outcome.SATISFIED,["EV-SITE"]),
        })

        slot=app.commands.reserve_slot(planner,"IDEMP-DEMO-1","P-A","SLOT-100",behavior="timeout_after_success")
        reconciled=app.commands.reconcile(planner,slot["command_id"])
        replay=app.commands.reserve_slot(planner,"IDEMP-DEMO-1","P-A","SLOT-100")

        quality_evidence: list[tuple[str, str, dict[str, Any]]] = [
            ("EV-MES","MES",{"status":"MFG_COMPLETE"}),
            ("EV-QC","LIMS",{"result":"PASS"}),
            ("EV-DEV","QMS",{"status":"CLOSED","blocking":False}),
            ("EV-THERMAL","LOGISTICS",{"status":"PROFILE_ACCEPTABLE"}),
            ("EV-QMS-DECISION","QMS",{"decision":"RELEASED","simulated":True}),
        ]
        for evidence_id, source, payload in quality_evidence:
            register(app,evidence_id,source,payload)
        app.quality.add_evidence("BATCH-100","EV-MES","MES_STATUS","MFG_COMPLETE")
        app.quality.add_evidence("BATCH-100","EV-QC","QC_RESULT","PASS",disposition="ACCEPTED")
        app.quality.add_evidence("BATCH-100","EV-DEV","DEVIATION","CLOSED",blocking=False)
        app.quality.add_evidence("BATCH-100","EV-THERMAL","THERMAL","PROFILE_ACCEPTABLE")
        before_release=app.quality.packet("BATCH-100")
        release=app.quality.authorize_release(quality_authority,"BATCH-100","EV-QMS-DECISION")
        after_release=app.quality.packet("BATCH-100")

        all_evidence=sorted(set(readiness.evidence_refs)|set(after_release["evidence_refs"]))
        domains=[
            {"domain":"Patient & Clinical","status":readiness.outcome.value,"detail":"Identity was resolved by the authorized role; consent, payer authorization and site readiness are satisfied.","evidence_refs":list(readiness.evidence_refs)},
            {"domain":"Logistics & Planning","status":"SATISFIED" if reconciled["state"]=="SUCCEEDED" and not replay["dispatch"] else "UNKNOWN","detail":"The slot timeout was reconciled to the existing reservation and duplicate dispatch was prevented.","evidence_refs":[]},
            {"domain":"Manufacturing","status":"SATISFIED","detail":"MES reports manufacturing complete; this is evidence, not Quality release authority.","evidence_refs":["EV-MES"]},
            {"domain":"Lab / QC","status":"SATISFIED","detail":"QC passed, the deviation is closed/non-blocking, and the thermal profile is acceptable.","evidence_refs":["EV-QC","EV-DEV","EV-THERMAL"]},
            {"domain":"Quality","status":after_release["release_outcome"],"detail":"The authorized Quality decision established release after the evidence packet was assembled.","evidence_refs":["EV-QMS-DECISION"]},
        ]
        ready=(readiness.outcome is Outcome.SATISFIED and reconciled["state"]=="SUCCEEDED" and not replay["dispatch"] and after_release["release_outcome"]=="SATISFIED")
        journey_summary={
            "patient_key":"P-A","batch_id":"BATCH-100",
            "overall_status":"READY_FOR_NEXT_AUTHORIZED_STEP" if ready else "BLOCKED_OR_UNKNOWN",
            "current_blocker":"NONE" if ready else "One or more deterministic gates remain unresolved",
            "next_owner":"Patient Operations Coordinator" if ready else "Owning domain authority",
            "risk":"LOW_IN_SYNTHETIC_DEMO_ONLY" if ready else "REVIEW_REQUIRED",
            "evidence_count":len(all_evidence),"open_exceptions":0 if ready else 1,
            "critical_checkpoint":{"before":before_release["release_outcome"],"blocker":"Authorized Quality release was required","owner":"Quality Authority","after":after_release["release_outcome"]},
            "summary":("Identity, consent, authorization and site readiness are satisfied; the manufacturing-slot timeout was reconciled without duplicate dispatch; manufacturing, QC, deviation and thermal evidence are acceptable; authorized Quality release is recorded. The synthetic journey is ready for the next authorized clinical/operations step." if ready else "The journey remains blocked or unknown and requires the owning domain authority to review cited evidence."),
            "domains":domains,"evidence_refs":all_evidence,
        }
        automation_trace=[
            {"step":"Identity exception detection","automation":"Automatic conflict detection and owned-case creation","human_boundary":"Identity Authority applies the final identity decision"},
            {"step":"Readiness evaluation","automation":"Deterministic gate evaluation across identity, consent, authorization and site readiness","human_boundary":"No clinical decision is automated"},
            {"step":"Slot orchestration","automation":"Unknown outcome reconciliation and duplicate-dispatch prevention","human_boundary":"Planner remains the authorized command actor"},
            {"step":"Quality evidence assembly","automation":"MES, QC, deviation and thermal evidence are assembled into the release packet","human_boundary":"Quality Authority makes the release decision"},
            {"step":"Cross-domain summary","automation":"The deterministic journey summary is generated from governed state and evidence","human_boundary":"The summary does not create authority or execute a consequential action"},
        ]
        recommendation=app.assistant.recommend("P-A/BATCH-100",{
            "state":journey_summary["overall_status"],"blockers":[] if ready else [journey_summary["current_blocker"]],
            "unknowns":[],"available_evidence":all_evidence,"deterministic_summary":journey_summary["summary"],
        })
        return {
            "scope":"SYNTHETIC_LOCAL_ACADEMIC_POC","ai_mode":ai_mode,
            "poc1":{"case":identity_case["case_id"],"decision":identity_decision["status"],"readiness":readiness.outcome.value,"evidence_refs":list(readiness.evidence_refs)},
            "poc2":{"initial_state":slot["state"],"reconciled_state":reconciled["state"],"replay_dispatch":replay["dispatch"]},
            "poc3":{"before":before_release["release_outcome"],"released":release["released"],"after":after_release["release_outcome"],"evidence_refs":after_release["evidence_refs"]},
            "journey_summary":journey_summary,"automation_trace":automation_trace,"role_views":ROLE_VIEWS,
            "information_architecture":{
                "structured_retrieval":"Typed source adapters, evidence registry and deterministic projections for authoritative operational facts.",
                "rag":"Not required for canonical state. Optional future RAG is limited to unstructured supporting evidence such as SOPs, emails and deviation narratives, with citations and version/freshness controls.",
                "mcp":"Not implemented in the current POC. MCP is a future enterprise integration option for approved read/tool adapters after identity, authorization and supplier controls are satisfied.",
            },
            "assistant":{"mode":recommendation["mode"],"rejection_reason":recommendation["rejection_reason"]},
            "assistant_output":recommendation["recommendation"],
            "audit_chain_valid":app.audit.verify()["chain_valid"],
            "governance":{"audit":app.audit.snapshot(limit=40)},
            "state_digest":app.db.state_digest(),"metrics":app.db.metrics(),
        }
    finally:
        app.close()
