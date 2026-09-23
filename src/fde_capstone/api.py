from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal

try:
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, ConfigDict, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install the api extra to run FastAPI") from exc

from . import frontend_mocks
from .application import CapstoneApplication
from .demo import run_demo
from .disruption_preview import list_injects, preview_inject
from .intelligence.digital_twin import twin_health
from .intelligence.exception_detector import detect_exceptions, detect_for_patient
from .model import Principal
from .reconciliation.patient_resolver import resolve_patient
from .security import AuthorizationError
from .services.common import authorize, correlation
from .source_cases import list_eval_cases, load_eval_case, reconstruct_source_journey

WEB_DIR = Path(__file__).with_name("web")
ROOT = Path(__file__).resolve().parents[2]
CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEMO_PERSONAS = (
    "Patient Operations",
    "Identity",
    "Logistics/Planning",
    "Manufacturing",
    "Lab/QC",
    "Quality",
    "Executive",
)
DEMO_LOGIN_TOKEN = "demo-token-123"
DEMO_NAV_ACTIONS = (
    "register_patient",
    "adjudicate_registration",
)
DEMO_ACCOUNTS = (
    {"username": "patient_ops", "display_name": "Patient Operations", "role_label": "Patient Operations Coordinator"},
    {"username": "identity", "display_name": "Identity", "role_label": "Identity Authority"},
    {"username": "logistics", "display_name": "Logistics/Planning", "role_label": "Logistics / Manufacturing Planner"},
    {"username": "manufacturing", "display_name": "Manufacturing", "role_label": "Manufacturing Operations"},
    {"username": "lab_qc", "display_name": "Lab/QC", "role_label": "Lab / Quality Control"},
    {"username": "quality", "display_name": "Quality", "role_label": "Quality Authority"},
    {"username": "executive", "display_name": "Executive", "role_label": "Executive / Operations Viewer"},
)


class DemoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = ""
    password: str = ""
    role: str = ""


class DemoRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_mode: Literal["off", "fake"] = "off"


class AgentInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: str = ""


class LoosePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReconcilePatientRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_key: str = ""
    orchestration_id: str = ""
    crm_id: str = ""
    clinical_id: str = ""
    mrn: str = ""


class SlotReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=200)
    patient_key: str = Field(min_length=1, max_length=200)
    slot_id: str = Field(min_length=1, max_length=200)
    behavior: Literal["success", "timeout_after_success", "partial", "failure"] = "success"


def _evidence_summary(path: str) -> dict[str, Any]:
    payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
    summary = payload.get("summary", payload)
    if not isinstance(summary, dict):
        raise ValueError(f"Expected object summary in {path}")
    return summary


def _identities_from_environment() -> dict[str, Principal]:
    """Load opaque bearer tokens mapped to server-side demo identities."""
    raw = os.getenv("FDE_DEMO_IDENTITIES_JSON", "")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FDE_DEMO_IDENTITIES_JSON must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("FDE_DEMO_IDENTITIES_JSON must be a token-to-identity object")
    identities: dict[str, Principal] = {}
    for token, claims in payload.items():
        if not isinstance(token, str) or not token or not isinstance(claims, dict):
            raise RuntimeError("Each demo identity requires a non-empty token and claim object")
        subject = claims.get("subject")
        roles = claims.get("roles")
        scopes = claims.get("scopes", ["*"])
        if not isinstance(subject, str) or not isinstance(roles, list) or not all(isinstance(x, str) for x in roles):
            raise RuntimeError("Each demo identity requires subject and string roles")
        if not isinstance(scopes, list) or not all(isinstance(x, str) for x in scopes):
            raise RuntimeError("Demo identity scopes must be a list of strings")
        identities[token] = Principal(subject, frozenset(roles), frozenset(scopes))
    return identities


def _resolve_demo_account(username: str = "", role: str = "") -> dict[str, str]:
    needle = (username or role or "").strip().lower()
    if needle:
        for account in DEMO_ACCOUNTS:
            haystack = {
                account["username"].lower(),
                account["display_name"].lower(),
                account["role_label"].lower(),
            }
            if needle in haystack or needle.replace(" ", "_") == account["username"]:
                return dict(account)
    return dict(DEMO_ACCOUNTS[0])


def _demo_session(account: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "success",
        "message": "Login successful",
        "token": DEMO_LOGIN_TOKEN,
        "role": {
            "name": account["username"],
            "label": account["role_label"],
            "description": f"{account['display_name']} demo persona. Synthetic academic only; not IAM.",
            "actions": list(DEMO_NAV_ACTIONS),
        },
        "user": {
            "username": account["username"],
            "display_name": account["display_name"],
            "identity": account["username"],
            "job_title": account["role_label"],
        },
        "persona": account["display_name"],
        "scope": "SYNTHETIC_DEMO_LOGIN",
    }


def _demo_overview() -> dict[str, Any]:
    return {
        "active_patients": 12,
        "pending_batches": 3,
        "exceptions": 1,
        "system_status": "operational",
        "sampled": 50,
        "policy_version": "academic-poc",
        "legacy_declared_ready": 9,
        "governed_declared_ready": 0,
        "identity_queue": 4,
        "coi_from_email": 2,
        "divergence": {"legacy_says_ready_but_qa_has_not_released": 6},
        "release_integrity": {"released_with_unresolved_qc": 1},
        "readiness": {
            "READY": 0,
            "BLOCKED": 22,
            "CONFLICT": 8,
            "UNKNOWN": 11,
            "NEEDS_EVIDENCE": 9,
        },
        "gate_failures": {
            "G1": 4,
            "G2": 3,
            "G3": 5,
            "G4": 2,
            "G5": 7,
            "G6": 9,
            "G7": 6,
            "G8": 8,
            "G9": 3,
            "G10": 50,
        },
        "scope": "SYNTHETIC_DASHBOARD_MOCK",
    }


def _demo_agents() -> dict[str, Any]:
    callers = [account["username"] for account in DEMO_ACCOUNTS]
    agents = [
        {
            "id": "AG-TRIAGE",
            "agent_id": "AG-TRIAGE",
            "name": "Triage Agent",
            "status": "ready",
            "action_class": "B",
            "purpose": "Rank open exceptions by patient impact. Advisory only; it cannot close a deviation or change readiness.",
            "authority": "Human reviewer",
            "prohibited": [
                "Merge patient identity",
                "Authorize QA release",
                "Dispatch a manufacturing slot",
            ],
            "contract": {
                "allowed_callers": callers,
                "data_classification": "synthetic-operational",
                "side_effects": "none",
                "approval_required": "No — recommendation only",
            },
        },
        {
            "id": "AG-QC",
            "agent_id": "AG-QC",
            "name": "QC Agent",
            "status": "ready",
            "action_class": "B",
            "purpose": "Summarize QC packet completeness. It cannot disposition a result or release a batch.",
            "authority": "Quality Authority",
            "prohibited": [
                "Disposition QC OOS",
                "Approve product release",
                "Alter MES or QMS state",
            ],
            "contract": {
                "allowed_callers": callers,
                "data_classification": "synthetic-qc",
                "side_effects": "none",
                "approval_required": "No — recommendation only",
            },
        },
    ]
    return {
        "principle": "Assistants explain and rank. Deterministic gates decide. Authorized humans act.",
        "model": {
            "name": "bounded-fake",
            "version": "off",
            "prompt_version": "academic-poc",
            "llm_configured": False,
        },
        "agents": agents,
        "no_agent_by_design": [
            {"action": "identity.merge", "authority": "Identity Authority"},
            {"action": "quality.release", "authority": "Quality Authority"},
            {"action": "slot.dispatch", "authority": "Manufacturing planner"},
        ],
        "scope": "SYNTHETIC_ADVISORY_AGENTS",
    }


def _demo_agent_result(agent_id: str, subject: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    catalogue = {agent["agent_id"]: agent for agent in _demo_agents()["agents"]}
    agent = catalogue.get(agent_id) or {
        "agent_id": agent_id,
        "name": agent_id,
        "action_class": "B",
        "authority": "Human reviewer",
    }
    target = subject or "cohort"
    return {
        "agent_id": agent["agent_id"],
        "action_class": agent.get("action_class", "B"),
        "subject": subject,
        "summary": "Patient data reconciled as an advisory view only. No identity merge, slot, or Quality release was applied.",
        "confidence": 0.74,
        "uncertainty": "Synthetic fixture. Rankings are not a clinical or Quality decision.",
        "required_authority": agent.get("authority", "Human reviewer"),
        "findings": [
            {"item": "Identity conflicts remain unresolved", "count": 4, "owner": "Identity Authority"},
            {"item": "QC packet incomplete at G6", "count": 9, "owner": "Lab / QC"},
        ],
        "evidence": [
            {
                "source": "source_baseline",
                "fact": "patient_key",
                "value": target,
                "ref": "frozen-csv",
                "trust": "UNKNOWN",
            }
        ],
        "model": {"name": "bounded-fake", "version": "off", "prompt_version": "academic-poc"},
        "invoked_at": now,
        "applied_automatically": False,
    }


_SEVERITY_SCORE = {"CRITICAL": 95, "HIGH": 82, "MAJOR": 74, "MEDIUM": 58, "LOW": 32}


def _normalize_intel_exception(row: dict[str, Any]) -> dict[str, Any]:
    severity = str(row.get("severity") or "HIGH").upper()
    patient = str(row.get("patient_key") or row.get("patient_id") or "")
    kind = str(row.get("exception_type") or row.get("kind") or "ANOMALY")
    systems = row.get("conflicting_systems") if isinstance(row.get("conflicting_systems"), list) else []
    evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
    drivers = [str(item) for item in systems if item]
    if not drivers:
        for item in evidence:
            if not isinstance(item, dict):
                continue
            value = item.get("note") or item.get("field") or item.get("eval")
            if value:
                drivers.append(str(value))
    if not drivers:
        drivers = [str(row.get("recommendation") or "Requires human review")]
    return {
        **row,
        "exception_id": row.get("exception_id") or "EXC-UNKNOWN",
        "patient_key": patient,
        "patient_id": patient,
        "kind": kind,
        "exception_type": kind,
        "severity": severity,
        "score": row.get("score") if isinstance(row.get("score"), (int, float)) else _SEVERITY_SCORE.get(severity, 70),
        "age_hours": row.get("age_hours") if isinstance(row.get("age_hours"), (int, float)) else 8,
        "owner": row.get("owner"),
        "authority": row.get("authority") or row.get("authority_requirement") or "Human reviewer",
        "drivers": drivers,
        "recommendation": row.get("recommendation") or "",
        "requires_human_review": True,
        "autonomous_action": "none",
        "evidence": evidence,
        "conflicting_systems": systems,
    }


def _public_intelligence_exceptions(patient_key: str | None = None, limit: int = 40) -> dict[str, Any]:
    try:
        rows = detect_for_patient(patient_key) if patient_key else detect_exceptions()
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []
    normalized = [_normalize_intel_exception(row) for row in rows if isinstance(row, dict)]
    ranked = [
        row
        for row in normalized
        if str(row.get("severity") or "").upper() in {"CRITICAL", "HIGH", "MAJOR"}
    ]
    cap = max(1, min(limit, 80))
    shown = ranked[:cap]
    return {
        "count": len(normalized),
        "shown": len(shown),
        "exceptions": shown,
        "method": "Ranked by severity from frozen source assertions. Observe/recommend only.",
        "requires_human_review": True,
        "autonomous_action": "none",
        "scope": "SYNTHETIC_SOURCE_ASSERTIONS_ONLY",
        "note": "Recommendations only. Does not change patient, batch, QMS, or shipment state.",
    }


def create_app(
    database_path: str | Path | None = None,
    demo_identities: Mapping[str, Principal] | None = None,
) -> FastAPI:
    resolved_database: str | Path = (
        database_path if database_path is not None else os.environ.get("FDE_DB", "runtime/api.db")
    )
    ai_mode = os.getenv("AI_MODE", "off")
    identities = dict(demo_identities) if demo_identities is not None else _identities_from_environment()

    def get_service() -> CapstoneApplication:
        service = getattr(app.state, "service", None)
        if service is None:
            service = CapstoneApplication(resolved_database, ai_mode=ai_mode)
            app.state.service = service
        return service

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        get_service()
        try:
            yield
        finally:
            service = getattr(app.state, "service", None)
            if service is not None:
                service.close()
                app.state.service = None

    app = FastAPI(
        title="FDE Final Capstone",
        version="1.2.0",
        description="Synthetic academic CGT patient-to-batch orchestration demonstration.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
        allow_headers=["*"],
    )
    app.state.service = None
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    def demo_principal(authorization: str | None) -> Principal:
        if not identities:
            raise HTTPException(503, "mutating demo API identities are not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "bearer token required")
        supplied = authorization.removeprefix("Bearer ").strip()
        matched = next((principal for token, principal in identities.items() if secrets.compare_digest(token, supplied)), None)
        if matched is None:
            raise HTTPException(401, "invalid bearer token")
        return matched

    @app.get("/health")
    def health() -> dict[str, Any]:
        service = get_service()
        return {
            "status": "ok",
            "scope": "synthetic-local-academic",
            "ai_mode": service.ai_mode,
            "audit_valid": service.db.verify_audit_chain(),
        }

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        payload = health()
        return {
            "status": "ok",
            "synthetic": True,
            "llm_configured": False,
            "policy_version": "academic-poc",
            "scope": payload["scope"],
            "ai_mode": payload["ai_mode"],
            "audit_valid": payload["audit_valid"],
        }

    @app.get("/api/auth/accounts")
    def auth_accounts() -> dict[str, Any]:
        return {
            "scope": "SYNTHETIC_DEMO_PERSONAS",
            "personas": list(DEMO_PERSONAS),
            "accounts": [dict(account) for account in DEMO_ACCOUNTS],
        }

    @app.get("/api/personas")
    def personas() -> dict[str, Any]:
        return auth_accounts()

    @app.post("/api/auth/login")
    def auth_login(payload: DemoLoginRequest | None = None) -> dict[str, Any]:
        requested = payload or DemoLoginRequest()
        account = _resolve_demo_account(requested.username, requested.role)
        return _demo_session(account)

    @app.get("/api/auth/me")
    def auth_me(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "bearer token required")
        token = authorization.removeprefix("Bearer ").strip()
        if token != DEMO_LOGIN_TOKEN:
            raise HTTPException(401, "invalid bearer token")
        return _demo_session(dict(DEMO_ACCOUNTS[0]))

    @app.post("/api/auth/logout")
    def auth_logout() -> dict[str, str]:
        return {"status": "success", "message": "Signed out"}

    @app.get("/api/overview")
    def api_overview() -> dict[str, Any]:
        return _demo_overview()

    @app.get("/api/agents")
    def api_agents() -> dict[str, Any]:
        return _demo_agents()

    @app.get("/api/agents/activity")
    def api_agent_activity(limit: int = 25) -> dict[str, Any]:
        return frontend_mocks.agent_activity(limit)

    @app.post("/api/agents/{agent_id}/invoke")
    def api_invoke_agent(agent_id: str, payload: AgentInvokeRequest | None = None) -> dict[str, Any]:
        requested = payload or AgentInvokeRequest()
        result = _demo_agent_result(agent_id, requested.subject)
        return {
            "status": "success",
            "message": f"{result['agent_id']} invoked successfully",
            "result": result,
        }

    def _body(payload: LoosePayload | None) -> dict[str, Any]:
        return payload.model_dump(exclude_none=False) if payload is not None else {}

    @app.get("/api/workflow")
    def api_workflow() -> dict[str, Any]:
        pipeline = frontend_mocks.workflow_pipeline()
        journey = frontend_mocks.patient_journey("P-00005")
        return {
            "sampled": pipeline["sampled"],
            "stages": pipeline["stages"],
            "journey": journey["stages"],
            "steps": journey["stages"],
            "patients": [journey],
            "scope": pipeline["scope"],
        }

    @app.get("/api/workflow/{patient_key}/timeline")
    def api_workflow_timeline(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.timeline(patient_key)

    @app.get("/api/workflow/{patient_key}/actions/{stage_id}")
    def api_workflow_action(patient_key: str, stage_id: str) -> dict[str, Any]:
        return frontend_mocks.stage_action(patient_key, stage_id)

    @app.post("/api/workflow/{patient_key}/actions/{stage_id}/decide")
    def api_workflow_decide(
        patient_key: str,
        stage_id: str,
        payload: LoosePayload | None = None,
    ) -> dict[str, Any]:
        return frontend_mocks.record_decision(patient_key, stage_id, _body(payload))

    @app.get("/api/workflow/{patient_key}")
    def api_workflow_patient(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.patient_journey(patient_key)

    @app.get("/api/journeys")
    def api_journeys(q: str = "", readiness: str = "", limit: int = 60) -> dict[str, Any]:
        return frontend_mocks.journeys(q, readiness, limit)

    @app.get("/api/journeys/{patient_key}")
    def api_journey_detail(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.journey_detail(patient_key)

    @app.get("/api/planning/projection")
    def api_planning(start: str = "2026-09-21") -> dict[str, Any]:
        return frontend_mocks.planning_projection(start)

    @app.get("/api/exceptions")
    def api_exceptions(limit: int = 25) -> dict[str, Any]:
        return frontend_mocks.exceptions(limit)

    @app.get("/api/capacity")
    def api_capacity() -> dict[str, Any]:
        return frontend_mocks.capacity()

    @app.get("/api/audit/access")
    def api_audit_access(limit: int = 40) -> dict[str, Any]:
        return frontend_mocks.audit_access(limit)

    @app.get("/api/audit/decisions")
    def api_audit_decisions(limit: int = 20) -> dict[str, Any]:
        return frontend_mocks.audit_decisions(limit)

    @app.get("/api/scheduling/board")
    def api_scheduling_board(limit: int = 40) -> dict[str, Any]:
        return frontend_mocks.scheduling_board(limit)

    @app.post("/api/scheduling/propose/{patient_key}")
    def api_scheduling_propose(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.propose_slot(patient_key)

    @app.post("/api/scheduling/approve/{patient_key}")
    def api_scheduling_approve(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.approve_slot(patient_key)

    @app.get("/api/enrolment/reference")
    def api_enrolment_reference() -> dict[str, Any]:
        return frontend_mocks.enrolment_reference()

    @app.get("/api/enrolment")
    def api_enrolment() -> dict[str, Any]:
        return frontend_mocks.enrolment_registry()

    @app.post("/api/enrolment/register")
    def api_enrolment_register(payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.enrol_register(_body(payload))

    @app.post("/api/enrolment/{registration_id}/decide/countersign")
    def api_enrolment_countersign(
        registration_id: str,
        payload: LoosePayload | None = None,
    ) -> dict[str, Any]:
        return frontend_mocks.enrol_countersign(registration_id, _body(payload))

    @app.post("/api/enrolment/{registration_id}/decide")
    def api_enrolment_decide(
        registration_id: str,
        payload: LoosePayload | None = None,
    ) -> dict[str, Any]:
        return frontend_mocks.enrol_decide(registration_id, _body(payload))

    @app.get("/api/tracking")
    def api_tracking(limit: int = 50, only_issues: bool = False) -> dict[str, Any]:
        return frontend_mocks.tracking_board(limit)

    @app.get("/api/tracking/{shipment_id}")
    def api_tracking_detail(shipment_id: str) -> dict[str, Any]:
        return frontend_mocks.tracking_detail(shipment_id)

    @app.get("/api/logistics/excursions")
    def api_logistics_excursions() -> dict[str, Any]:
        return frontend_mocks.logistics_excursions()

    @app.get("/api/intake/samples")
    def api_intake_samples() -> dict[str, Any]:
        return frontend_mocks.intake_samples()

    @app.get("/api/intake")
    def api_intake() -> dict[str, Any]:
        return frontend_mocks.intake()

    @app.post("/api/intake/upload")
    def api_intake_upload(payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.intake_upload(_body(payload))

    @app.post("/api/intake/proposals/{proposal_id}/decide")
    def api_intake_decide(proposal_id: str, payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.intake_decide(proposal_id, _body(payload))

    @app.get("/api/identity/queue")
    def api_identity_queue(limit: int = 40) -> dict[str, Any]:
        return frontend_mocks.identity_queue(limit)

    @app.post("/api/identity/{patient_key}/merge")
    def api_identity_merge(patient_key: str) -> dict[str, Any]:
        return frontend_mocks.identity_merge(patient_key)

    @app.get("/api/evidence/documents")
    def api_evidence_documents() -> dict[str, Any]:
        return frontend_mocks.evidence_documents()

    @app.post("/api/evidence/probe")
    def api_evidence_probe(payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.evidence_probe(_body(payload))

    @app.get("/api/approvals")
    def api_approvals(action: str = "release_product") -> dict[str, Any]:
        return frontend_mocks.approvals(action)

    @app.post("/api/release/{patient_key}/approve")
    def api_release_approve(patient_key: str, payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.release_approve(patient_key, _body(payload))

    @app.post("/api/release/{patient_key}/countersign")
    def api_release_countersign(patient_key: str, payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.release_countersign(patient_key, _body(payload))

    @app.post("/api/release/{patient_key}/reject")
    def api_release_reject(patient_key: str, payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.release_reject(patient_key, _body(payload))

    @app.post("/api/rejections/{rejection_id}/withdraw")
    def api_withdraw_rejection(rejection_id: str, payload: LoosePayload | None = None) -> dict[str, Any]:
        return frontend_mocks.withdraw_rejection(rejection_id, _body(payload))

    @app.get("/api/lots/{lot_id}/reviewer-packet")
    def api_reviewer_packet(lot_id: str) -> dict[str, Any]:
        return frontend_mocks.reviewer_packet(lot_id)

    @app.post("/api/attestations/{attestation_id}/withdraw")
    def api_withdraw_attestation(attestation_id: str) -> dict[str, Any]:
        return frontend_mocks.withdraw_attestation(attestation_id)

    @app.get("/api/intelligence/exceptions")
    def api_intelligence_exceptions(patient_key: str | None = None, limit: int = 40) -> dict[str, Any]:
        return _public_intelligence_exceptions(patient_key, limit)

    @app.get("/api/intelligence/digital-twin")
    def api_digital_twin() -> dict[str, Any]:
        payload = twin_health()
        payload.setdefault("systems", [])
        payload.setdefault("signals", [])
        payload.setdefault("anomalies", [])
        return payload

    @app.post("/api/reconciliation/patient")
    def api_reconcile_patient(payload: ReconcilePatientRequest | None = None) -> dict[str, Any]:
        body = payload or ReconcilePatientRequest()
        key = (body.patient_key or body.orchestration_id or "").strip()
        result = resolve_patient(
            orchestration_id=key or None,
            crm_id=body.crm_id or None,
            clinical_id=body.clinical_id or None,
            mrn=body.mrn or None,
        )
        confidence = result.get("confidence_score")
        return {
            "patient_key": key,
            "resolved_patient_key": result.get("resolved_patient_key") or "",
            "confidence_score": confidence if isinstance(confidence, (int, float)) else 0.0,
            "requires_human_review": bool(result.get("requires_human_review", True)),
            "conflicts": result.get("conflicts") if isinstance(result.get("conflicts"), list) else [],
            "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
            "authority_requirement": result.get("authority_requirement") or "human-chain-of-identity",
            "rule_version": result.get("rule_version"),
            "reconciliation": result,
            "result": result,
            "autonomous_action": "none",
            "scope": "SYNTHETIC_SOURCE_ASSERTIONS_ONLY",
            "note": "Evidence pack only. Does not merge identity or rewrite source rows.",
        }

    @app.get("/", include_in_schema=False)
    def control_tower() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/capstone/status")
    def capstone_status() -> dict[str, Any]:
        service = get_service()
        tests = _evidence_summary("docs/stages/stage_15/test_summary.json")
        evaluation = _evidence_summary("docs/stages/stage_15/evaluation_results.json")
        requirements = _evidence_summary("requirements/verification_matrix.json")
        return {
            "status": "READY_FOR_SYNTHETIC_DEMO",
            "scope": "SYNTHETIC_LOCAL_ACADEMIC_POC",
            "stages": {"documented": 21, "total": 21, "externally_approved": False},
            "tests": {
                "passed": tests["passed"],
                "failed": tests["failures"] + tests["errors"],
                "scope": "LOCAL_AUTOMATED",
            },
            "evaluations": {
                "structural_passes": evaluation["pass"],
                "failed": evaluation["fail"],
                "inconclusive_human_studies": evaluation["inconclusive"],
                "property_coverage": evaluation["property_coverage"],
            },
            "requirements": {
                "verified_internal_poc": requirements["verified_internal_poc"],
                "external_evidence_required": requirements["inconclusive_external_evidence_required"],
                "total": requirements["total"],
                "production_verified": requirements["production_verified"],
            },
            "ai_mode": service.ai_mode,
            "audit_valid": service.db.verify_audit_chain(),
            "lifecycle_decision": "RESTRICT_AND_CHANGE",
            "production_authorized": False,
        }

    @app.post("/api/demo/run")
    def execute_demo(payload: DemoRunRequest | None = None) -> dict[str, Any]:
        requested = payload or DemoRunRequest()
        with TemporaryDirectory(prefix="fde-capstone-web-demo-") as directory:
            return run_demo(Path(directory) / "demo.db", ai_mode=requested.ai_mode)

    @app.get("/api/source/cases")
    def source_case_list() -> dict[str, Any]:
        try:
            cases = list_eval_cases()
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"scope": "FROZEN_V2_SOURCE_READ_ONLY_SYNTHETIC", "cases": cases}

    @app.get("/api/source/cases/{case_id}")
    def source_case_detail(case_id: str) -> dict[str, Any]:
        try:
            detail = load_eval_case(case_id)
            detail["timestamp_order_reconstruction"] = reconstruct_source_journey(case_id)
            return detail
        except KeyError as exc:
            raise HTTPException(404, "source case not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/source/injects")
    def source_inject_list() -> dict[str, Any]:
        try:
            injects = list_injects()
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"scope": "FROZEN_V2_SOURCE_SCENARIO_PREVIEW_NOT_EXECUTED", "injects": injects}

    @app.get("/api/source/injects/{inject_id}/preview")
    def source_inject_preview(inject_id: str, patient_key: str = "P-00001") -> dict[str, Any]:
        try:
            return preview_inject(inject_id, patient_key)
        except KeyError as exc:
            raise HTTPException(404, "inject or representative patient not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/quality/{batch_id}/packet")
    def quality_packet(batch_id: str) -> dict[str, Any]:
        return get_service().quality.packet(batch_id)

    @app.get("/commands/{command_id}")
    def command(command_id: str) -> dict[str, Any]:
        try:
            return get_service().commands.get(command_id)
        except KeyError as exc:
            raise HTTPException(404, "command not found") from exc

    @app.post("/slots/reservations")
    def reserve_slot(
        payload: SlotReservationRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = demo_principal(authorization)
        try:
            return get_service().commands.reserve_slot(
                principal,
                payload.idempotency_key,
                payload.patient_key,
                payload.slot_id,
                payload.behavior,
            )
        except AuthorizationError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/reconcile/patient")
    def reconcile_patient(
        orchestration_id: str | None = None,
        crm_id: str | None = None,
        clinical_id: str | None = None,
        mrn: str | None = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = demo_principal(authorization)
        service = get_service()
        trace = correlation()
        try:
            authorize(service.db, principal, "read", "*", trace)
        except AuthorizationError as exc:
            raise HTTPException(403, str(exc)) from exc
        result = resolve_patient(
            orchestration_id=orchestration_id,
            crm_id=crm_id,
            clinical_id=clinical_id,
            mrn=mrn,
        )
        scope = result.get("resolved_patient_key") or "*"
        service.audit.record(
            principal,
            "read",
            scope,
            "ALLOWED",
            {
                "endpoint": "/reconcile/patient",
                "rule_version": result.get("rule_version"),
                "requires_human_review": result.get("requires_human_review"),
            },
            trace,
        )
        service.db.metric("patient_reconcile")
        return result

    @app.get("/intelligence/exceptions")
    def intelligence_exceptions(
        patient_key: str | None = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = demo_principal(authorization)
        service = get_service()
        trace = correlation()
        scope = patient_key or "*"
        try:
            authorize(service.db, principal, "read", scope, trace)
        except AuthorizationError as exc:
            raise HTTPException(403, str(exc)) from exc
        rows = detect_for_patient(patient_key) if patient_key else detect_exceptions()
        service.audit.record(
            principal,
            "read",
            scope,
            "ALLOWED",
            {
                "endpoint": "/intelligence/exceptions",
                "count": len(rows),
            },
            trace,
        )
        service.db.metric("intelligence_exceptions")
        return {
            "count": len(rows),
            "exceptions": rows,
            "requires_human_review": True,
            "autonomous_action": "none",
            "scope": "SYNTHETIC_SOURCE_ASSERTIONS_ONLY",
            "note": "Recommendations only. Does not change patient, batch, QMS, or shipment state.",
        }

    @app.get("/api/governance/identity")
    def governance_identity(
        orchestration_id: str | None = None,
        crm_id: str | None = None,
        clinical_id: str | None = None,
        mrn: str | None = None,
    ) -> dict[str, Any]:
        result = resolve_patient(
            orchestration_id=orchestration_id,
            crm_id=crm_id,
            clinical_id=clinical_id,
            mrn=mrn,
        )
        return {
            "scope": "SYNTHETIC_SOURCE_ASSERTIONS_ONLY",
            "autonomous_action": "none",
            "note": "Evidence pack only. Does not merge identity or rewrite source rows.",
            **result,
        }

    @app.get("/api/governance/exceptions")
    def governance_exceptions(patient_key: str | None = None, limit: int = 12) -> dict[str, Any]:
        rows = detect_for_patient(patient_key) if patient_key else detect_exceptions()
        cap = max(1, min(limit, 40))
        return {
            "count": len(rows),
            "shown": min(len(rows), cap),
            "exceptions": rows[:cap],
            "requires_human_review": True,
            "autonomous_action": "none",
            "scope": "SYNTHETIC_SOURCE_ASSERTIONS_ONLY",
            "note": "Recommendations only. Does not change patient, batch, QMS, or shipment state.",
        }

    @app.get("/api/governance/audit")
    def governance_audit(limit: int = 40) -> dict[str, Any]:
        snapshot = get_service().audit.snapshot(limit=limit)
        return {
            "scope": "SYNTHETIC_LOCAL_ACADEMIC_POC",
            **snapshot,
        }

    return app


# ASGI import target. Database creation is deferred to application lifespan,
# so importing this module does not leak an in-memory SQLite connection.
app = create_app()
