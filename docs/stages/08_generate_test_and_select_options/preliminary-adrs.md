# Preliminary ADRs

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 08 — Generate, Test & Select Options  
**Participant status:** `COMPLETED`  
**Deliverable form:** ADR / decision record  
**Linked selection:** D2 in `08_generate_test_and_select_options/trade-off-matrix.md`

Three architecture decisions already encoded in `src/cgt_orchestrator/`. Each follows Title / Status / Context / Decision / Consequences.

---

## ADR-001 — Explicit state machines for journey and release gates

**Status:** Accepted (implemented)

### Context
Legacy `product_ready()` treated MES `MFG_COMPLETE`/`RELEASED` **or** ERP `AVAILABLE` as product release (`14_engineer/technical-defect-resolution-report.md` Defect 1). `patient_ready()` treated `journey_status != ENROLLED` as a proxy for continuation and ignored consent. Homonymous strings (`RELEASED` in MES vs QMS) collapsed QC complete, QA released, product ready and infusion ready (`.cursor/rules/cgt-fde.mdc` item 3). `AGENTS.md` requires explicit state machines over strings scattered in code. SOP-QA-014 v4: manufacturing completion is not product release (`docs/sops/SOP-QA-014-v4.md`).

### Options
| Option | Evidence | Outcome |
|---|---|---|
| Keep string flags / OR-logic | Pre-fix `status_rules.py`; xfail `test_product_not_ready_until_qa_released` | Rejected — 16 MES vs QMS conflicts in `data/raw/batches.csv` |
| Full journey_status state machine rewriting `data/raw/patients.csv` | 10 observed statuses in patients.csv | Rejected — would “clean” challenge data (`AGENTS.md`) |
| Enumerated **gate** machines; leave `journey_status` as observed evidence | `QmsReleaseState`, `ConsentState` | **Selected** |

### Decision
Implement `QmsReleaseState` (`PENDING` / `HOLD` / `RELEASED`) and `ConsentState` (`VALID` / `EXPIRED_VERSION` / `WITHDRAWN`) in `src/cgt_orchestrator/legacy/status_rules.py`. `product_ready()` is true only when QMS parses to `RELEASED` (and blocking deviations / required QC when supplied). `patient_ready()` is false on `WITHDRAWN` / `EXPIRED_VERSION` (EVAL-004, `data/raw/consents.csv` CNS-00157). `journey_status` remains a source-qualified observation, not a single “ready” flag. `/legacy/readiness/{patient_key}` in `src/cgt_orchestrator/api.py` must keep its non-clinical warning.

### Consequences
- **Positive:** FR-04/FR-05 gates are testable (`tests/test_legacy_expected_failures.py`); MES `RELEASED` no longer authorizes product.
- **Negative:** `journey_status` is still a free string on the patient row; a full journey FSM is future work.
- **Reversal:** Re-introduce OR-logic only with a documented SOP change and a new failing test first.

---

## ADR-002 — Bounded agency with HITL for exception intelligence

**Status:** Accepted (implemented)

### Context
FR-06 required ranked cross-system exceptions, not unranked `/exceptions` deviations (`src/cgt_orchestrator/repository.py` `open_deviations`). `AGENTS.md` forbids autonomous QA / COI / COC. EVAL-004: no autonomous continuation after consent withdrawal. EVAL-006: untrusted documents are data, not commands.

### Options
| Option | Evidence | Outcome |
|---|---|---|
| LLM chatbot / RAG as the decision surface | Rejected A1 in trade-off matrix | Fails local-first and EVAL-006 |
| Write-capable agents (auto-release, auto-merge) | Rejected A2 | Violates non-negotiables |
| Observe / correlate / recommend + HITL receipt | `exception_detector.py`; `acknowledge_store.py` | **Selected** |

### Decision
POC 2 (`src/cgt_orchestrator/intelligence/exception_detector.py`) emits exceptions with `requires_human_review=True` and `autonomous_action=none`. `POST /api/exceptions/{id}/acknowledge` (`src/cgt_orchestrator/intelligence/exceptions_routes.py`) records a human receipt only (`effect_on_systems_of_record=none` in `acknowledge_store.py`). Dashboard: `static/exceptions_dashboard.html`. Identity remains a separate read-only tool (`src/cgt_orchestrator/reconciliation/patient_resolver.py`; EVAL-002). No path sets `qms_release_status`.

### Consequences
- **Positive:** 263 ranked exceptions on seed 42001; pytest `tests/test_exception_intelligence.py` locks HITL.
- **Negative:** Acknowledgements are in-process memory (lost on restart); not a durable GxP audit log.
- **Reversal:** Kill the correlator if any code path writes QMS, merges `patient_key`, or drops `requires_human_review`.

---

## ADR-003 — Local-first execution (no cloud for baseline)

**Status:** Accepted (implemented)

### Context
`AGENTS.md` Local-first: essential orchestration must run without cloud credentials; optional LLM adapters default off. NFR-01 in `13_approve_adrs_and_delivery_specification/delivery-specification.md`. `VERIFICATION.md`: external consequential-control integration disabled. Estate is synthetic (`README.md`, `data/manifest.json` seed 42001).

### Options
| Option | Evidence | Outcome |
|---|---|---|
| Cloud LLM required for exceptions | Would couple `/api/exceptions/active` to a vendor | Rejected — essential path would fail offline |
| Graph/RAG platform as system of record | `docs/04_target_capabilities_not_prescribed_solutions.md` | Rejected as prescribed solution |
| Local FastAPI + SQLite + CSV + pytest | `requirements.txt`; `data/cgt_legacy.db`; `data/raw/` | **Selected** |

### Decision
Baseline runtime is `uvicorn` + FastAPI (`src/cgt_orchestrator/api.py`), SQLite via `src/cgt_orchestrator/paths.py` (`data/cgt_legacy.db`), identity from CSVs (`data/raw/patients.csv`, `crm_patient_export.csv`, `clinical_patient_export.csv`), CLI (`src/cgt_orchestrator/cli.py`). Dependencies: `fastapi`, `uvicorn`, `pytest` only (`requirements.txt`). Optional LLM remains **not present** (off by default). Bind is demo-local; AuthN/Z is an open gap, not a cloud substitute.

### Consequences
- **Positive:** Pytest and detector run without credentials; degraded mode is the CLI (`diagnostics` / `exceptions`).
- **Negative:** No managed identity, no durable audit SaaS, CORS `allow_origins=["*"]` is demo-only.
- **Reversal:** Introduce a cloud adapter only as an optional extra, default-disabled, that cannot be the release or identity authority.

## Evidence and traceability
| Claim / decision | Evidence | Confidence |
|---|---|---|
| ADR-001 implemented | `src/cgt_orchestrator/legacy/status_rules.py` `QmsReleaseState`, `ConsentState` | High |
| ADR-002 implemented | `exception_detector.py` `_exception()`; `acknowledge_store.py` | High |
| ADR-003 implemented | `requirements.txt`; `AGENTS.md`; `VERIFICATION.md` | High |

## Handoff
**Stage exit contribution:** Approved solution and trade-offs — ADRs-001–003 bind Stage 10 containers.
