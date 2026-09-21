# CGT Control Tower Demo Guide

## Fastest start on macOS

Double-click `START_DEMO.command` in Finder. On first use it creates the local `.venv` and installs the project dependencies. Keep the terminal window open while presenting. The Control Tower opens automatically at <http://127.0.0.1:8000>.

The application uses disposable synthetic data only. Stop it with `Control-C` in the terminal.

## Terminal start

```bash
cd /Users/suryap/Documents/Codex/2026-09-11/i/FDE-Final-Capstone
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,api]'
FDE_DB=runtime/control-tower.db AI_MODE=off PYTHONPATH=src \
  .venv/bin/python -m uvicorn fde_capstone.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. API documentation remains available at <http://127.0.0.1:8000/docs>.

## Presentation sequence (about eight minutes)

The Control Tower is an **application shell**: left rail, command bar (patient/batch, assistant mode, **Run journey**), and one workspace at a time. It is not a long marketing page.

1. Start on **Overview**. State the problem: fragmented systems cannot safely answer the current patient-to-batch state, why it is true, who can decide and what must happen next. The telemetry strip and cassette panel are the live context.
2. Point to the four controls on the cassette: human-authorized identity, idempotent orchestration, retained Quality authority and AI off by default. The vein-to-vein track lights as the demo runs.
3. Open **Source cases** in the rail. Inspect `EVAL-002`: original patient rows, contradictory source assertions, file/row locators and the collapsible **source-timestamp journey order**. Open `EVAL-003` to show that sorting a contradictory arrival/departure does not repair it. For `EVAL-005/006`, distinguish the hypothetical stimulus from observed facts. These six examples are read-only occurrence-time ordering, not known-at replay, migration or adjudication.
4. In the command bar keep **AI off · recommended**, then choose **Run journey**. The workspace switches to **Live demo**. This run uses a *separate scripted POC fixture*, not the EVAL-002 patient.
5. Explain POC 1: conflicting identity evidence creates an owned case; an authorized simulated human applies the exact reviewed proposal; readiness becomes `SATISFIED` with citations.
6. Explain POC 2: the simulated external reservation succeeds but times out. The system records `OUTCOME_UNKNOWN`, reconciles it to `SUCCEEDED`, and prevents a second dispatch.
7. Explain POC 3: manufacturing, QC, deviation and thermal evidence still leave release `UNKNOWN`; only the simulated Quality-authority decision makes it `SATISFIED`.
8. Return to **Source cases** and preview `INJ-001` or `INJ-008`: point to downstream dependency/route risk and owner. The zero-slack shift is a stated assumption; no route, slot, quality or clinical plan is committed.
9. Show the evidence console on **Live demo**: cited references, a valid audit chain, deterministic AI-off mode, metrics and a state digest.
10. Close on **Boundaries**: **21/21 stages documented**, local tests, **55/57 catalog cases structurally pass** (only 7 original cases have full scoped property assertions, 9 partial, 39 extensions structural-only), and **29/31 requirements locally verified**. The two remaining requirements need controlled human studies; the registered 20-client/full-dataset NFR is not verified.
11. State the honest decision: **RESTRICT AND CHANGE**. The academic demo is built; production and real-data use remain prohibited until the seven CAPAs and accountable gates are closed.

## Optional bounded-assistant demonstration

Choose **Bounded fake adapter** and run again. This exercises the recommendation contract without calling a live model. Domain outcomes must remain the same. It is not evidence of live-model quality or production AI readiness.

## What the demo must not claim

- No real patient, clinical, manufacturing or Quality data is used.
- The demo principals are not enterprise IAM or electronic signatures.
- External systems and decision authorities are simulated.
- No live AI provider or model is connected.
- The project does not establish clinical benefit, regulatory compliance, production safety, savings or ROI.

## Role-based and automation demo add-on

Before running the three POCs, open **Role workspace** in the rail. Switch through Patient Operations, Identity Authority, Logistics/Planner, Manufacturing, Lab/QC and Quality Authority. Explain that these are persona lenses over the same governed journey and do not grant new backend permissions.

Run with **AI off · recommended** first. After the run, show the **automated cross-domain summary** and the automation trace. The summary shows the five domains, current blocker, next owner and evidence count. Then optionally run with **Bounded fake adapter** to show that AI explanation is additive: underlying journey state and domain authority do not change.

## Identity, exceptions and tamper-evident audit

The Control Tower **Governance** workspace uses the same command-shell visual language as the rest of the app. It is observe/recommend only.

1. Open **Governance** in the rail. The snapshot strip shows the current identity lookup, how many exceptions are on screen, and whether the live hash chain verifies.
2. **Patient identity evidence:** keep `P-00001` or enter another synthetic key / MRN and choose **Inspect identity**. Show confidence, the HITL flag and any DOB/MRN conflicts. Emphasize that this evidence pack does not merge records. For a conflicting case, inspect frozen `EVAL-002` in the source-evidence section, then return here to show the same refusal to auto-link.
3. **Cross-system exception queue:** choose **Load exceptions** (optionally filter `P-00001`). Point to severity, conflicting systems encoded in the type name, and the recommendation that always requires human review. Nothing in this queue writes MES, QMS or shipment state.
4. Run the end-to-end demo, then look at **Tamper-evident audit trail**. The demo-run chain is populated from the disposable POC ledger (`governance.audit` in the demo payload). Each row carries `previous_hash` / `record_hash`. **Refresh live ledger** reads `/api/governance/audit` on the server database — it may be empty until a bearer-authenticated command runs against `FDE_DB`.
5. If you need the authenticated surfaces, call `GET /reconcile/patient` and `GET /intelligence/exceptions` with a configured demo bearer token. Those routes audit the access itself onto the same SQLite hash chain via `AuditService`.

Do not present the React files under `src/fde_capstone/web_frontend/` as the live Control Tower. That drop-in is a richer client prototype; the packaged demonstration is `src/fde_capstone/web/`.
