import json

import pytest
from fastapi.testclient import TestClient

from fde_capstone.model import Principal


def test_api_exposes_health_and_bounded_poc_routes(tmp_path):
    from fde_capstone.api import create_app

    app = create_app(tmp_path / "api.db")
    with TestClient(app):
        paths = {route.path for route in app.routes}
        assert "/" in paths
        assert "/health" in paths
        assert "/api/health" in paths
        assert "/api/auth/accounts" in paths
        assert "/api/auth/login" in paths
        assert "/api/personas" in paths
        assert "/api/capstone/status" in paths
        assert "/api/demo/run" in paths
        assert "/api/source/cases" in paths
        assert "/api/source/cases/{case_id}" in paths
        assert "/api/source/injects" in paths
        assert "/api/source/injects/{inject_id}/preview" in paths
        assert "/quality/{batch_id}/packet" in paths
        assert "/slots/reservations" in paths
        assert "/reconcile/patient" in paths
        assert "/intelligence/exceptions" in paths
        assert "/api/governance/identity" in paths
        assert "/api/governance/exceptions" in paths
        assert "/api/governance/audit" in paths
        assert "/api/overview" in paths
        assert "/api/agents" in paths
        assert "/api/agents/activity" in paths
        assert "/api/agents/{agent_id}/invoke" in paths
        assert "/api/workflow" in paths
        assert "/api/workflow/{patient_key}" in paths
        assert "/api/journeys" in paths
        assert "/api/enrolment" in paths
        assert "/api/tracking" in paths
        assert "/api/intake" in paths
        assert "/api/intelligence/exceptions" in paths
        assert "/api/intelligence/digital-twin" in paths
        assert "/api/reconciliation/patient" in paths
        assert not any("release/auto" in path for path in paths)
        assert not any(
            "agent" in path and not path.startswith("/api/agents")
            for path in paths
        )
    assert app.state.service is None


def test_react_frontend_health_and_demo_personas_are_public(tmp_path):
    from fde_capstone.api import DEMO_PERSONAS, create_app

    with TestClient(create_app(tmp_path / "frontend-auth.db")) as client:
        health = client.get("/api/health")
        accounts = client.get("/api/auth/accounts")
        personas = client.get("/api/personas")
        preflight = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["synthetic"] is True
    assert accounts.status_code == 200
    body = accounts.json()
    assert body["personas"] == list(DEMO_PERSONAS)
    assert [row["display_name"] for row in body["accounts"]] == list(DEMO_PERSONAS)
    assert all({"username", "display_name", "role_label"} <= row.keys() for row in body["accounts"])
    assert personas.json()["personas"] == list(DEMO_PERSONAS)
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_demo_login_bypasses_auth_and_returns_frontend_session(tmp_path):
    from fde_capstone.api import DEMO_LOGIN_TOKEN, create_app

    with TestClient(create_app(tmp_path / "demo-login.db")) as client:
        preflight = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        response = client.post(
            "/api/auth/login",
            json={"username": "quality", "password": "ignored"},
        )
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {DEMO_LOGIN_TOKEN}"})
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in (preflight.headers.get("access-control-allow-methods") or "").upper()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Login successful"
    assert body["token"] == DEMO_LOGIN_TOKEN
    assert body["user"]["display_name"] == "Quality"
    assert body["role"]["label"] == "Quality Authority"
    assert "register_patient" in body["role"]["actions"]
    assert me.status_code == 200
    assert me.json()["token"] == DEMO_LOGIN_TOKEN


def test_dashboard_overview_and_advisory_agents_are_mocked(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "dashboard-mock.db")) as client:
        overview = client.get("/api/overview")
        agents = client.get("/api/agents")
        invoke = client.post("/api/agents/AG-TRIAGE/invoke", json={"subject": "P-00001"})
        preflight = client.options(
            "/api/agents/AG-TRIAGE/invoke",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
    assert overview.status_code == 200
    body = overview.json()
    assert body["system_status"] == "operational"
    assert body["active_patients"] == 12
    assert "readiness" in body and "gate_failures" in body
    assert agents.status_code == 200
    catalogue = agents.json()
    assert [row["id"] for row in catalogue["agents"]] == ["AG-TRIAGE", "AG-QC"]
    assert invoke.status_code == 200
    payload = invoke.json()
    assert payload["status"] == "success"
    assert payload["result"]["agent_id"] == "AG-TRIAGE"
    assert payload["result"]["summary"]
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_react_dashboard_mocks_return_mappable_arrays(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "frontend-mocks.db")) as client:
        workflow = client.get("/api/workflow")
        patient = client.get("/api/workflow/P-00005")
        timeline = client.get("/api/workflow/P-00005/timeline")
        journeys = client.get("/api/journeys")
        exceptions = client.get("/api/exceptions")
        capacity = client.get("/api/capacity")
        tracking = client.get("/api/tracking")
        intake = client.get("/api/intake")
        identity = client.get("/api/identity/queue")
        decide = client.post(
            "/api/workflow/P-00005/actions/S02/decide",
            json={"decision": "acknowledge", "justification": "Recorded in the academic demo.", "e_signature": "Demo Reviewer"},
        )
        preflight = client.options(
            "/api/workflow/P-00005",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert workflow.status_code == 200
    pipeline = workflow.json()
    assert isinstance(pipeline["stages"], list) and len(pipeline["stages"]) >= 4
    assert isinstance(pipeline["journey"], list) and len(pipeline["journey"]) >= 4
    assert isinstance(pipeline["steps"], list) and len(pipeline["steps"]) >= 4
    assert all("counts" in stage for stage in pipeline["stages"])
    assert patient.status_code == 200
    journey = patient.json()
    assert isinstance(journey["stages"], list) and len(journey["stages"]) >= 4
    assert all(isinstance(stage["gate_ids"], list) for stage in journey["stages"])
    assert timeline.status_code == 200
    assert isinstance(timeline.json()["projection"]["steps"], list)
    assert isinstance(timeline.json()["waiting_on"], list)
    assert journeys.status_code == 200
    assert isinstance(journeys.json()["journeys"], list)
    assert exceptions.status_code == 200
    assert isinstance(exceptions.json()["exceptions"], list)
    assert capacity.status_code == 200
    assert isinstance(capacity.json()["sites"], list)
    assert tracking.status_code == 200
    assert isinstance(tracking.json()["shipments"], list)
    assert intake.status_code == 200
    assert isinstance(intake.json()["records"], list)
    assert isinstance(intake.json()["pending"], list)
    assert identity.status_code == 200
    assert isinstance(identity.json()["queue"], list)
    assert decide.status_code == 200
    assert decide.json()["decision"]["decision_id"]
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_intelligence_and_reconciliation_are_wired_for_the_react_app(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "intel-ui.db")) as client:
        exceptions = client.get("/api/intelligence/exceptions")
        twin = client.get("/api/intelligence/digital-twin")
        reconcile = client.post("/api/reconciliation/patient", json={"patient_key": "P-00001"})
        preflight = client.options(
            "/api/reconciliation/patient",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert exceptions.status_code == 200
    body = exceptions.json()
    assert isinstance(body["exceptions"], list)
    assert body["autonomous_action"] == "none"
    assert body["requires_human_review"] is True
    for row in body["exceptions"]:
        assert isinstance(row.get("drivers"), list)
        assert "patient_key" in row
    assert twin.status_code == 200
    health = twin.json()
    assert health["status"] in {"HEALTHY", "DEGRADED"}
    assert isinstance(health["systems"], list) and health["systems"]
    assert isinstance(health["anomalies"], list)
    assert health["autonomous_action"] == "none"
    assert reconcile.status_code == 200
    resolved = reconcile.json()
    assert resolved["patient_key"] == "P-00001"
    assert resolved["resolved_patient_key"] == "P-00001"
    assert isinstance(resolved["confidence_score"], (int, float))
    assert isinstance(resolved["evidence"], list) and resolved["evidence"]
    assert resolved["autonomous_action"] == "none"
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_control_tower_status_is_honest_about_scope(tmp_path):
    from fde_capstone.api import ROOT, create_app

    with TestClient(create_app(tmp_path / "status.db")) as client:
        result = client.get("/api/capstone/status").json()
    assert result["stages"] == {"documented": 21, "total": 21, "externally_approved": False}
    assert result["tests"]["passed"] == json.loads(
        (ROOT / "docs/stages/stage_15/test_summary.json").read_text()
    )["passed"]
    assert result["evaluations"]["property_coverage"]["FULL_SCOPED_PROPERTY_ASSERTIONS"] == 7
    assert result["requirements"]["total"] == 31
    assert result["production_authorized"] is False
    assert result["lifecycle_decision"] == "RESTRICT_AND_CHANGE"


def test_control_tower_executes_all_three_pocs(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "demo-route.db")) as client:
        response = client.post("/api/demo/run", json={"ai_mode": "off"})
    assert response.status_code == 200
    result = response.json()
    assert result["poc1"]["readiness"] == "SATISFIED"
    assert result["poc2"]["initial_state"] == "OUTCOME_UNKNOWN"
    assert result["poc2"]["reconciled_state"] == "SUCCEEDED"
    assert result["poc3"]["released"] is True
    assert result["audit_chain_valid"] is True
    assert result["governance"]["audit"]["chain_valid"] is True
    assert result["governance"]["audit"]["entries"] >= 1
    assert result["journey_summary"]["overall_status"] == "READY_FOR_NEXT_AUTHORIZED_STEP"
    assert result["journey_summary"]["current_blocker"] == "NONE"
    assert result["journey_summary"]["evidence_count"] == 10
    assert len(result["journey_summary"]["domains"]) == 5
    assert len(result["role_views"]) == 7
    assert {role["backend_role"] for role in result["role_views"]} >= {
        "COORDINATOR",
        "IDENTITY_AUTHORITY",
        "PLANNER",
        "QUALITY_AUTHORITY",
        "VIEWER",
    }
    assert len(result["automation_trace"]) == 5
    assert "deterministic projections" in result["information_architecture"]["structured_retrieval"]
    assert "Optional future RAG" in result["information_architecture"]["rag"]
    assert "Not implemented" in result["information_architecture"]["mcp"]
    assert result["audit_chain_valid"] is True


def test_control_tower_page_is_packaged(tmp_path):
    from fde_capstone.api import WEB_DIR, create_app

    assert (WEB_DIR / "index.html").is_file()
    assert (WEB_DIR / "styles.css").is_file()
    assert (WEB_DIR / "app.js").is_file()
    assert (WEB_DIR / "favicon.svg").is_file()
    with TestClient(create_app(tmp_path / "page.db")) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "FDE" in response.text


def test_read_only_v2_source_routes_are_explicitly_non_authoritative(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "source.db")) as client:
        case = client.get("/api/source/cases/EVAL-002").json()
        preview = client.get("/api/source/injects/INJ-008/preview", params={"patient_key": "P-00001"}).json()
    assert case["observations"][0]["status"] == "OBSERVED_CONFLICT"
    assert case["disposition"] == "NONE_SOURCE_ASSERTIONS_ONLY"
    assert case["timestamp_order_reconstruction"]["control_gates"]["identity"] == (
        "CONFLICT_REQUIRES_AUTHORIZED_REVIEW"
    )
    assert preview["side_effects"] == 0
    assert preview["affected_routes"]


def test_pydantic_rejects_unapproved_ai_mode_and_missing_reservation_fields(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "validation.db")) as client:
        invalid_mode = client.post("/api/demo/run", json={"ai_mode": "live"})
        missing_fields = client.post("/slots/reservations", json={"patient_key": "P-1"})
    assert invalid_mode.status_code == 422
    assert missing_fields.status_code == 422


def test_mutating_route_uses_server_side_bearer_identity_not_role_headers(tmp_path):
    from fde_capstone.api import create_app

    planner = Principal("configured-planner", frozenset({"PLANNER"}), frozenset({"*"}))
    app = create_app(tmp_path / "auth.db", demo_identities={"opaque-test-token": planner})
    payload = {"idempotency_key": "IDEMP-1", "patient_key": "P-1", "slot_id": "S-1"}
    with TestClient(app) as client:
        unsigned = client.post(
            "/slots/reservations",
            json=payload,
            headers={"x-principal": "attacker", "x-role": "QUALITY_AUTHORITY"},
        )
        invalid = client.post(
            "/slots/reservations",
            json=payload,
            headers={"authorization": "Bearer wrong-token"},
        )
        valid = client.post(
            "/slots/reservations",
            json=payload,
            headers={"authorization": "Bearer opaque-test-token"},
        )
    assert unsigned.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["state"] == "SUCCEEDED"


def test_mutating_route_fails_closed_when_no_demo_identity_is_configured(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "closed.db", demo_identities={})) as client:
        response = client.post(
            "/slots/reservations",
            json={"idempotency_key": "I", "patient_key": "P", "slot_id": "S"},
            headers={"authorization": "Bearer anything"},
        )
    assert response.status_code == 503


def test_demo_identity_configuration_is_loaded_from_environment(monkeypatch):
    from fde_capstone.api import _identities_from_environment

    monkeypatch.setenv(
        "FDE_DEMO_IDENTITIES_JSON",
        json.dumps(
            {
                "opaque-token": {
                    "subject": "demo-planner",
                    "roles": ["PLANNER"],
                    "scopes": ["site:alpha"],
                }
            }
        ),
    )
    identities = _identities_from_environment()
    assert identities["opaque-token"] == Principal(
        "demo-planner",
        frozenset({"PLANNER"}),
        frozenset({"site:alpha"}),
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-json", "valid JSON"),
        ("[]", "token-to-identity object"),
        ('{"": {}}', "non-empty token"),
        ('{"token": {"subject": 7, "roles": ["PLANNER"]}}', "subject and string roles"),
        ('{"token": {"subject": "planner", "roles": ["PLANNER"], "scopes": "*"}}', "list of strings"),
    ],
)
def test_demo_identity_configuration_rejects_malformed_claims(monkeypatch, raw, message):
    from fde_capstone.api import _identities_from_environment

    monkeypatch.setenv("FDE_DEMO_IDENTITIES_JSON", raw)
    with pytest.raises(RuntimeError, match=message):
        _identities_from_environment()


def test_api_translates_source_failures_to_bounded_http_errors(tmp_path, monkeypatch):
    import fde_capstone.api as api_module

    def missing_source(*_args, **_kwargs):
        raise FileNotFoundError("frozen source unavailable")

    def unknown_source(*_args, **_kwargs):
        raise KeyError("unknown")

    app = api_module.create_app(tmp_path / "errors.db")
    with TestClient(app) as client:
        monkeypatch.setattr(api_module, "list_eval_cases", missing_source)
        assert client.get("/api/source/cases").status_code == 503
        monkeypatch.setattr(api_module, "load_eval_case", unknown_source)
        assert client.get("/api/source/cases/UNKNOWN").status_code == 404
        monkeypatch.setattr(api_module, "list_injects", missing_source)
        assert client.get("/api/source/injects").status_code == 503
        monkeypatch.setattr(api_module, "preview_inject", unknown_source)
        assert client.get("/api/source/injects/UNKNOWN/preview").status_code == 404


def test_api_reports_missing_commands_and_forbidden_reservations(tmp_path):
    from fde_capstone.api import create_app

    viewer = Principal("configured-viewer", frozenset({"VIEWER"}), frozenset({"*"}))
    app = create_app(tmp_path / "bounded-errors.db", demo_identities={"viewer-token": viewer})
    with TestClient(app) as client:
        missing = client.get("/commands/UNKNOWN")
        forbidden = client.post(
            "/slots/reservations",
            json={"idempotency_key": "I", "patient_key": "P", "slot_id": "S"},
            headers={"authorization": "Bearer viewer-token"},
        )
        packet = client.get("/quality/UNKNOWN/packet")
    assert missing.status_code == 404
    assert forbidden.status_code == 403
    assert packet.status_code == 200
    assert packet.json()["batch_id"] == "UNKNOWN"


def test_reconcile_and_intelligence_routes_require_configured_bearer_identity(tmp_path):
    from fde_capstone.api import create_app

    viewer = Principal("configured-viewer", frozenset({"VIEWER"}), frozenset({"*"}))
    app = create_app(tmp_path / "intel-auth.db", demo_identities={"viewer-token": viewer})
    with TestClient(app) as client:
        unsigned = client.get("/reconcile/patient", params={"orchestration_id": "P-00001"})
        invalid = client.get(
            "/intelligence/exceptions",
            headers={"authorization": "Bearer wrong-token"},
        )
        reconcile = client.get(
            "/reconcile/patient",
            params={"orchestration_id": "P-00001"},
            headers={"authorization": "Bearer viewer-token"},
        )
        exceptions = client.get(
            "/intelligence/exceptions",
            params={"patient_key": "P-00001"},
            headers={"authorization": "Bearer viewer-token"},
        )
    assert unsigned.status_code == 401
    assert invalid.status_code == 401
    assert reconcile.status_code == 200
    payload = reconcile.json()
    assert payload["resolved_patient_key"] == "P-00001"
    assert payload["requires_human_review"] in {True, False}
    assert payload["evidence"]
    assert exceptions.status_code == 200
    body = exceptions.json()
    assert body["autonomous_action"] == "none"
    assert body["requires_human_review"] is True
    assert isinstance(body["exceptions"], list)


def test_reconcile_and_intelligence_routes_fail_closed_without_demo_identities(tmp_path):
    from fde_capstone.api import create_app

    with TestClient(create_app(tmp_path / "intel-closed.db", demo_identities={})) as client:
        reconcile = client.get(
            "/reconcile/patient",
            params={"mrn": "MRN-741568"},
            headers={"authorization": "Bearer anything"},
        )
        exceptions = client.get(
            "/intelligence/exceptions",
            headers={"authorization": "Bearer anything"},
        )
    assert reconcile.status_code == 503
    assert exceptions.status_code == 503


def test_governance_preview_routes_are_read_only_synthetic(tmp_path):
    from fde_capstone.api import create_app

    app = create_app(tmp_path / "governance.db")
    with TestClient(app) as client:
        identity = client.get("/api/governance/identity", params={"orchestration_id": "P-00001"})
        exceptions = client.get("/api/governance/exceptions", params={"patient_key": "P-00001", "limit": 5})
        audit = client.get("/api/governance/audit")
    assert identity.status_code == 200
    assert identity.json()["resolved_patient_key"] == "P-00001"
    assert identity.json()["autonomous_action"] == "none"
    assert exceptions.status_code == 200
    assert exceptions.json()["requires_human_review"] is True
    assert exceptions.json()["autonomous_action"] == "none"
    assert audit.status_code == 200
    assert audit.json()["chain_valid"] is True
    assert audit.json()["genesis"] == "GENESIS"
