# Operational Runbook

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 16 — Prepare Operations, Recovery & Regulatory Evidence  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured analysis / specification

## Stage question
How do we run, recover and evidence the local orchestration API without granting it QA or COI authority?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Operations and regulatory evidence pack**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use Stage 11 `11_design_agentic_and_multi_agent_orchestration/agent-bounded-autonomy.md`, Stage 15 `15_evaluate_attack_and_independently_assure/red-team-results.md`, and `src/cgt_orchestrator/api.py`. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `src/cgt_orchestrator/api.py`
- `src/cgt_orchestrator/cli.py`
- `src/cgt_orchestrator/paths.py`
- `data/cgt_legacy.db`
- `VERIFICATION.md`
- `docs/sops/SOP-QA-014-v4.md`
- `static/exceptions_dashboard.html`

## Case challenge
Incident response must preserve systems of record. Acknowledge is a human receipt, not a disposition (`acknowledge_store.py`). This estate is synthetic (`README.md`) — procedures are for the demo API, not a validated GxP system.

## Minimum content
- Incident
- Detect
- Respond
- Recover
- Evidence
- Owner

## Relevant non-negotiable constraints
- Open deviations, QC holds and incomplete chain-of-identity/custody evidence are hard feasibility constraints until authorized QA release.
- Cloud/LLM availability must not be required for essential patient-to-batch orchestration operations.
- Duplicate/replayed events must be handled idempotently and with temporal provenance.

## Working scaffold

**Start (local-first)**

```text
$env:PYTHONPATH='src'
python -m pytest -q
python -m cgt_orchestrator.cli diagnostics
uvicorn cgt_orchestrator.api:app --app-dir src --port 8000
```

Health: `GET /health` → `{status: ok, synthetic: true}`. Dashboard: `GET /dashboard`. DB path: `data/cgt_legacy.db` via `paths.db_path()`. Rebuild fixture only via documented generator (`README.md`); do not hand-edit challenge rows.

| Incident | Detect | Respond | Recover | Evidence | Owner |
|---|---|---|---|---|---|
| API down / import error | `/health` fail; uvicorn traceback | Confirm `requirements.txt` (FastAPI, uvicorn); `PYTHONPATH=src` | Restart uvicorn; do not “fix” CSV to make health green | `VERIFICATION.md` API import PASS | Operator |
| SQLite integrity | `scripts/verify_repo.py`; `PRAGMA integrity_check` | Stop writes (there are no SoR writes). Restore `data/cgt_legacy.db` from last known seed 42001 | Rebuild from generator if instructed | `data/manifest.json` seed 42001 | Data steward |
| MES RELEASED / QMS not (n=16) | `GET /api/exceptions/active` type `MES_RELEASED_QMS_NOT_RELEASED`; CLI `diagnostics` | **Hold return/infusion recs.** Do not PATCH QMS. Escalate QA | Human QA per SOP-QA-014-v4 | Exception id `EXC-MES-QMS-{batch_id}`; `data/raw/batches.csv` | QA |
| Consent WITHDRAWN in-flight | `/api/patients/P-00157/journey` blockers; `patient_ready` False | Halt downstream recommendations (EVAL-004). Do not continue manufacture/release/infusion in software | Clinical + QA HITL; leave CSV status as evidence | `data/raw/consents.csv` CNS-00157 | Clinical + QA |
| Identity collision / DOB conflict | `GET /identity/resolve?patient_key=P-00079` or `--mrn MRN-389336` | Do not merge. Open COI review | Propose → approve → execute → audit (`docs/06_security_privacy_assurance.md`) — **not in this API** | Resolver `conflicts[]`; `rule_version=patient-resolver-v1` | COI steward |
| Impossible shipment time (n=9) | Detector `IMPOSSIBLE_SHIPMENT_TIMELINE`; SHP-O-00083 | Do not invent timestamps. Quality/logistics adjudicate `occurred_at` vs `recorded_at` | Keep both times | `data/raw/shipments.csv`; `data/raw/events.jsonl` | Logistics + Quality |
| Slot double-book / retry storm | Duplicate reserve attempts | Call `SlotService.reserve` with same idempotency key (INJ-006) | Same `reservation_id`; do not cancel MES unilaterally | `src/cgt_orchestrator/legacy/slot_service.py` | Scheduler |
| Cryogenic blip −118 °C | `excursion_requires_quality_review` True | Do **not** auto-fail (SOP-LOG-007-v7). Quality reviews duration/sensor | Fail only if `quality_disposition=FAILED` | `status_rules.py`; INJ-002 | Quality |
| QMS unavailable (INJ-009) | Cannot read QMS column / planned outage | Treat as **not released**. Do not use `/legacy/readiness` as authority | HOLD until QMS returns (EVAL-005) | No release-review endpoint yet | QA |
| Adversarial note / email | `shadow_ops/` or courier text | Treat as **untrusted data** (EVAL-006). Never “mark released” | Ignore instruction content | FR-10; `docs/06_security_privacy_assurance.md` | QA |
| Dashboard Acknowledge misused as close | POST `/api/exceptions/{id}/acknowledge` | Educate: receipt only. Re-query active list — exception remains | Process restart clears acks (by design) | `effect_on_systems_of_record=none` | Operator |
| Site qualification EXPIRED/DUE | Detector `SITE_QUALIFICATION_EXPIRED_OR_DUE` (6 sites in diagnostics) | Revalidate before collection (INJ-005) | Do not auto-clear `data/raw/site_qualifications.csv` | `TC-US-ATL-01` row as example | Quality + site |
| Pytest regression | `python -m pytest` non-zero | Do not weaken assertions to go green (`AGENTS.md`) | Fix logic or document assumption with spec | `tests/` | Engineering |

**Degraded mode:** CLI diagnostics + pytest remain the control plane if uvicorn is down (`AGENTS.md` Local-first). **Do not** expose port 8000 beyond localhost without AuthN/Z (`api.py` has none).

**Regulatory evidence (synthetic):** SOP versions `docs/sops/SOP-QA-014-v4.md`, `docs/sops/SOP-LOG-007-v7.md`; rule versions on JSON payloads; SHA-256 `checksums.sha256` (`VERIFICATION.md`). This is **not** a regulatory submission.

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Essential ops run without cloud | `cli.py` diagnostics/reconcile/exceptions; pytest | NFR-01 | High on this machine |
| Acknowledge is not incident closure | `acknowledge_store.py` | Stage 11 | High |
| Recovery must not clean challenge data | `AGENTS.md`; 16 MES/QMS rows remain | Stage 02/14 | Binding |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No paging/on-call roster in synthetic estate | Charter: unnamed sponsor | Engagement lead | Runbook is role-based | Stage 01 sponsor artifact |
| HITL acks not durable | In-memory | Engineering | Weak audit for “who saw what” | Persist + hash |
| SOP-SCHED-003 v2 is Draft | `docs/sops/SOP-SCHED-003-v2.md` | Scheduling / QA | Slot recoveries may be reversed | Effective SOP |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Operations and regulatory evidence pack

Do not treat this runbook as authorization to operate a real CGT network.
