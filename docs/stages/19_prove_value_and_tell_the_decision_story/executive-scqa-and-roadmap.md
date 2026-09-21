# Executive SCQA and 90-Day Roadmap

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Audience:** Senior leadership / trainer executive demo  
**Duration:** 10 minutes  
**Estate:** Synthetic brownfield, seed **42001**, **800** patients (`data/manifest.json`)  
**Governing rules:** `AGENTS.md`, `.cursor/rules/cgt-fde.mdc`, `docs/sops/SOP-QA-014-v4.md`, `docs/sops/SOP-LOG-007-v7.md`  
**Spec:** `13_approve_adrs_and_delivery_specification/delivery-specification.md`  
**Defect register:** `14_engineer/technical-defect-resolution-report.md`

This is the spoken narrative. Every number below is in the repository. Baseline KPIs are **synthetic and direction-only** (`data/reference/baseline_kpis.csv` `target_direction`; NFR-09 / Stage 01: do not invent percentage-point SLOs).

---

## 0:00–0:30 — Opening line

> Autologous CGT does not fail as a chatbot problem. It fails as an **operational-truth** problem: CRM, MES, QMS, scheduler and logistics disagree, operators reconcile in email, and a single overloaded “ready” flag can put a patient at risk. We inherited a runnable estate that was semantically unsafe. In this increment we closed the unsafe gates with **deterministic engineering**, then put **exception intelligence with human-in-the-loop** on top — observe, correlate, recommend. We did not give the model QA Release Authority.

---

## Situation (0:30–2:00)

**What the business asked for.** Senior leadership wants the next product generation to scale globally while reducing patient-at-risk cases, manual coordination and avoidable delays (`participant/CHALLENGE_BRIEF.md`). Mandate: operational truth and governed decision support, not a chatbot (`01_mandate_and_field_immersion/engagement-charter.md`).

**What the estate actually is.** A multinational orchestration landscape, locally runnable, no cloud credentials required (`AGENTS.md` Local-first):

| Scale | Evidence |
|---|---|
| 800 patients, 800 collections, 1,600 shipments, 800 batches, 188 deviations, 24 treatment centers, 6 manufacturing sites | `data/manifest.json`; `python -m cgt_orchestrator.cli diagnostics` → `patient_count=800` |
| Journey language is already overloaded: IN_MANUFACTURING 138, QA_HOLD 59, INFUSION_READY 57, INFUSED 127 | `data/raw/patients.csv`; `02_discover_process_and_architecture/brownfield-assessment.md` L5 |
| Shadow operations sit beside systems of record | `shadow_ops/PatientPriority_MASTER.csv`; `shadow_ops/ManufacturingSlots_FINAL_v7.csv` (`EMAIL OVERRIDE — moved Thu`); 21 OPEN courier escalations |

**Baseline operating cost of the current state** (`data/reference/baseline_kpis.csv`):

| KPI | Baseline | Direction we must move |
|---|---|---|
| Journeys requiring **manual reconciliation** | **31.5%** | DOWN |
| Avoidable delay hours / 100 journeys | **186** | DOWN |
| On-time infusion probability | **78.0%** | UP |
| Identity reconciliation exceptions / 1,000 | **17** | DOWN |
| Open-exception mean age | **29.4 hours** | DOWN |
| Manual status updates / journey | **12.7** | DOWN |
| Median vein-to-vein | **21.8 days** | DOWN |
| Slot utilization | **71.0%** | UP |
| QA-release forecast MAE | **27.5 hours** | DOWN |
| Cross-system traceability complete | **82.4%** | UP |

**Already quantified challenge signals** (`VERIFICATION.md`; `src/cgt_orchestrator/diagnostics.py`):

- Duplicate MRNs: **2**
- Impossible shipment timelines (`arrived_at` < `departed_at`): **9** (including SHP-O-00083)
- MES `RELEASED` while QMS is not: **16**
- Scheduler `CONFIRMED` + MES `CANCELLED`: **9**
- Withdrawn consents: **5** (including P-00157 / EVAL-004)
- Expired or due site controls: **6**

**Talking point:** QC complete, QA released, product ready and infusion ready must not collapse into one status. Manufacturing complete is not product release (`docs/sops/SOP-QA-014-v4.md`).

---

## Complication (2:00–4:00)

The brownfield was **runnable but semantically unsafe**. Three tests were marked `xfail` on purpose — they were a defect register, not flaky CI (`tests/test_legacy_expected_failures.py`, documented in `14_engineer/technical-defect-resolution-report.md`).

### Defect 1 — QA release conflated with manufacturing complete (FR-04)

Legacy `product_ready()` returned True if MES was `MFG_COMPLETE`/`RELEASED` **or** ERP was `AVAILABLE`. A batch with `qms_release_status=PENDING` was labelled ready.

> Trainer line: *“We were one OR-clause away from shipping a batch QA had not released.”*

**So what:** 16 MES-vs-QMS conflicts in `data/raw/batches.csv`; 73 OPEN + 62 INVESTIGATING deviations in `data/raw/deviations.csv`. That is a patient-safety and GxP story, not a UI defect.

### Defect 2 — Cryogenic excursion auto-failed from a single sensor point (FR-08)

Code implemented **superseded** SOP-LOG-007 v6: `temp_c > -120.0` was automatic shipment failure. Effective policy is v7 (`docs/sops/SOP-LOG-007-v7.md`, Effective 2026-05-01). A −118 °C blip (INJ-002) became a computer disposition.

> Trainer line: *“A two-degree blip is a Quality review, not a death sentence for the batch.”*

**So what:** False-failing a patient-specific batch forces recast into an already 21.8-day vein-to-vein clock.

### Defect 3 — Slot retries minted a new UUID (FR-07 / INJ-006)

Every `SlotService.reserve()` created a new `reservation_id`. An integration timeout-and-retry double-booked scarce suite time (baseline slot utilization 71.0%).

> Trainer line: *“A retry is not a second patient.”*

### Related gate — Consent ignored (FR-05 / EVAL-004)

`patient_ready()` ignored consent. P-00157 is `WITHDRAWN` (`data/raw/consents.csv` CNS-00157) while authorization is still `APPROVED` and journey is `IN_MANUFACTURING`. Continuing manufacture after withdrawal is unauthorized processing of human material.

### Identity is not a single key (FR-02 / EVAL-002)

CRM, clinical and orchestration identifiers coexist (`data/raw/patients.csv`, `data/raw/crm_patient_export.csv`, `data/raw/clinical_patient_export.csv`). P-00079: CRM DOB `1959-12-23` vs clinical/orchestration `1959-12-22`. SQLite `patients.dob` already dropped the CRM disagreement — **one database is not the source of truth**. Duplicate MRNs `MRN-389336` (P-00532 / P-00713) and `MRN-945144` (P-00686 / P-00755) would fuse two people if we joined on MRN.

**What we refused:** globally rewriting the 16 MES/QMS rows, picking a “winner” DOB, or adding an LLM to judge conflicts (`AGENTS.md`; report section “What we deliberately did *not* do”).

---

## Question (4:00–4:20)

**How might we reduce patient-at-risk cases while scaling globally — without making clinical, quality-release, chain-of-identity or chain-of-custody decisions autonomous?**

Sub-questions the demo answers:

1. Can we stop the software from lying about “ready”?
2. Can we show identity and cross-system contradictions as **evidence**, not silent merges?
3. Can AI/agents sit on that substrate with **bounded agency** (observe / correlate / recommend) and HITL receipts that do not write systems of record?

---

## Answer — The solution (4:20–7:00)

Two increments. Deterministic first. Agentic second. Local-first throughout.

### POC 1 — Patient identifier reconciliation (deterministic)

| | |
|---|---|
| Spec | FR-02, EVAL-002 |
| Code | `src/cgt_orchestrator/reconciliation/patient_resolver.py` |
| Tests | `tests/test_patient_reconciliation.py` |
| Surfaces | `python -m cgt_orchestrator.cli reconcile --patient-key P-00079` · `GET /identity/resolve` |

**Behavior:** Read-only correlator across three CSVs. If identifiers imply more than one `patient_key` → empty resolved key, confidence `0.0`, `requires_human_review=True`. If they agree on one key but DOB disagrees (P-00079) → confidence **0.55**, both DOBs retained in `evidence`, **no `canonical_dob`**. Authority: `human-chain-of-identity`. No write-back to CRM/QMS.

**Demo beat:** *“We would rather show a 0.55 confidence and a DOB conflict than invent a patient.”*

Also in this increment — the three xfail conversions plus consent gating (`src/cgt_orchestrator/legacy/status_rules.py`, `src/cgt_orchestrator/legacy/slot_service.py`):

- Explicit `QmsReleaseState` / `ConsentState` machines. `product_ready` is false until QMS `RELEASED` (and blocking deviations / required QC when supplied).
- `excursion_failed(-118)` is False unless Quality recorded `quality_disposition=FAILED`; `excursion_requires_quality_review` is the HITL flag.
- Slot reserve is idempotent on `patient_key:site_id` (or caller `idempotency_key`).
- `/legacy/readiness/{patient_key}` still warns it is **not** a validated clinical/quality decision.

### POC 2 — Exception Intelligence API (bounded agentic / HITL)

| | |
|---|---|
| Spec | FR-03, FR-06, Agent/HITL table in the delivery specification |
| Detector | `src/cgt_orchestrator/intelligence/exception_detector.py` (`exception-detector-v1`) |
| HITL store | `src/cgt_orchestrator/intelligence/acknowledge_store.py` |
| Routes | `src/cgt_orchestrator/intelligence/exceptions_routes.py` included from `src/cgt_orchestrator/api.py` |
| Dashboard | `static/exceptions_dashboard.html` → `GET /dashboard` |
| Tests | `tests/test_exception_intelligence.py` |
| CLI | `python -m cgt_orchestrator.cli exceptions` |

**Endpoints**

- `GET /api/exceptions/active` — ranked contradictions with `patient_id`, `exception_type`, `severity`, `conflicting_systems`, `evidence`, `requires_human_review: true`, `autonomous_action: none`
- `GET /api/patients/{patient_id}/journey` — journey rows **plus** blockers (P-00157 returns consent-blocking HITL)
- `POST /api/exceptions/{exception_id}/acknowledge` — human receipt only; `effect_on_systems_of_record: none`

**Live detector output on this fixture (seed 42001):** **263** exceptions, **100%** `requires_human_review`, autonomy **none**.

| Type | Count | Severity band | Tied to |
|---|---|---|---|
| OPEN_QUALITY_DEVIATION | 135 | CRITICAL / MAJOR | 73 OPEN + 62 INVESTIGATING |
| SITE_QUALIFICATION_EXPIRED_OR_DUE | 48 | HIGH | 6 expired/due sites × in-window patients |
| CONSENT_BLOCKING_IN_FLIGHT_JOURNEY | 42 | CRITICAL | WITHDRAWN + EXPIRED_VERSION in-flight (diagnostics withdrawn=5; detector also flags expired-version) |
| MES_RELEASED_QMS_NOT_RELEASED | 16 | HIGH | diagnostics = 16 |
| SCHEDULER_CONFIRMED_MES_CANCELLED | 9 | HIGH | diagnostics = 9 |
| IMPOSSIBLE_SHIPMENT_TIMELINE | 9 | HIGH | diagnostics = 9; EVAL-003 |
| DUPLICATE_MRN_IDENTITY_COLLISION | 4 | CRITICAL | 2 colliding pairs from `data/raw/patients.csv`, not SQLite |

**Demo beat:** Open `/dashboard`. Filter CRITICAL. Click **Acknowledge** on P-00157. Show the payload still says HITL required and QMS is unchanged. Then `GET /identity/resolve?patient_key=P-00079` to prove identity is a separate, explainable evidence pack.

---

## Data-driven impact (7:00–8:30)

Two layers. Do not conflate them.

### Layer A — Software gates we can prove *now* (this repo)

| Gate | Before (legacy) | After (this increment) | Proof |
|---|---|---|---|
| `product_ready` on MES complete + ERP available + QMS PENDING | **True** (unsafe) | **False** | `tests/test_legacy_expected_failures.py` |
| Single −118 °C point | Automatic fail (SOP v6) | Review flag; fail only on human `FAILED` | same file + `excursion_requires_quality_review` |
| Slot retry P-00001 / MFG-US-NJ-01 | New UUID each call | Same `reservation_id` | `test_slot_retry_is_idempotent` |
| Consent WITHDRAWN | Ignored | Blocks `patient_ready` | `test_withdrawn_consent_blocks_patient_ready`; EVAL-004 |
| P-00079 DOB conflict | Invisible in SQLite | Confidence **0.55**, HITL, both DOBs | `tests/test_patient_reconciliation.py` |
| Duplicate MRN | Join hazard | Empty resolved key; no merge | resolver + detector |
| `/exceptions` | Unranked non-CLOSED deviations | **263** typed, ranked, evidenced exceptions | `GET /api/exceptions/active` |
| Pytest | 2 passed, **3 xfailed** (`VERIFICATION.md`) | **25 passed**, 0 xfail | `python -m pytest` |
| Autonomy on exceptions | Boolean “ready” hid uncertainty | `autonomous_action=none` on every row | `tests/test_exception_intelligence.py` |

### Layer B — Operating KPIs (direction, not invented deltas)

`data/reference/baseline_kpis.csv` has **no numeric target**. Delivery specification open issue: *“Numeric SLO deltas (e.g. cut 31.5% reconciliation to X%) are not in-repo.”*

What this increment **enables** toward those directions:

| Baseline KPI | Mechanism now in code | Why it should move the right way |
|---|---|---|
| 31.5% manual reconciliation | Typed exceptions + identity evidence packs replace email archaeology | Operators see MES/QMS, slot, consent, MRN, timeline conflicts in one API |
| 12.7 manual status updates / journey | Source-qualified statuses preserved; no silent overwrite of QMS with MES (FR-09) | Fewer “which system is right?” pings |
| 17 identity exceptions / 1,000 | Resolver refuses merge; detector flags both MRN pairs | Exceptions become reviewable work, not silent wrong-patient risk |
| 29.4 h open-exception age | Ranked CRITICAL/HIGH queue + HITL acknowledge | Age becomes measurable from first detection |
| 186 avoidable delay hours / 100 | Idempotent slots; excursion review vs scrap; no false QA-release | Fewer recast and double-book cascades |
| 78% on-time infusion | Consent/site/QA gates fire *before* infusion scheduling | Late discovery becomes early hold |
| 71% slot utilization | Idempotent reserve (INJ-006) | Ghost holds stop stealing waitlist capacity |

**What did not change on purpose:** the 16 MES/QMS rows, 9 impossible shipments, P-00079 DOBs, duplicate MRNs. Those remain challenge signals (`AGENTS.md`). We changed **decision logic**, not the evidence.

---

## Repo 3.0 moonshot — 90-day roadmap (8:30–10:00)

Capabilities, not a prescribed knowledge graph, RAG stack or multi-agent mesh (`docs/04_target_capabilities_not_prescribed_solutions.md`). Optional LLM adapters stay **off by default**. Consequential QA / COI / COC remain human.

### Days 0–30 — Predictive logistics (still HITL)

| Outcome | Build | Hard stop |
|---|---|---|
| Duration/quality/cumulative cryogenic profile per SOP-LOG-007 v7 | Extend `excursion_requires_quality_review` with typed telemetry from `data/raw/cryogenic_telemetry.csv`; surface INJ-002 as a Quality pack | No auto-fail, no auto-reroute |
| Impossible-timeline adjudication | EVAL-003: keep `occurred_at` vs `recorded_at` (`data/raw/events.jsonl`); recommend source inquiry | Do not invent a corrected timeline |
| Courier disruption playbook | INJ-008 + `shadow_ops/CourierEscalations.csv` as **untrusted notes** (EVAL-006) | Email is data, not a release command |
| KPI instrumentation | Wire detector timestamps to `open_exception_mean_age_hours` without inventing an SLO | Product owner signs numeric targets |

### Days 31–60 — Multi-agent orchestration (bounded)

Use the already-scaffolded Stage 11 operating model (`participant_artifacts/11_design_agentic_and_multi_agent_orchestration/autonomy-level-adr.md`, `human-approval-override-escalation-matrix.md`, `tool-action-catalogue.md`):

| Agent | Autonomy | Tools it may call |
|---|---|---|
| Identity correlator | Observe | `patient_resolver`, `/identity/resolve` |
| Exception ranker | Observe / recommend | `exception_detector`, `/api/exceptions/active` |
| Release-pack assembler | Recommend only | QC + deviations + telemetry → `POST /recommendations/release-review` (specified, not yet executed) |
| Slot tool | Deterministic | Idempotent `reserve`; never cancel MES unilaterally |

**Shared memory:** exception ids, evidence pointers, rule versions — not a silent canonical patient. **Termination:** EVAL-004 consent halt; EVAL-005 QMS outage → HOLD; EVAL-006 adversarial note → no release. Human approval matrix remains the control plane.

### Days 61–90 — Digital twin of the vein-to-vein clock

A **simulation twin**, not a second master data store:

1. Replay `scenarios/inject_catalog.csv` INJ-001–010 against the 800-patient fixture (apheresis delay, suite outage, sterility backlog, courier disruption, QMS outage, authorization withdrawn).
2. Forecast QA-release time as an **uncertainty band** (baseline MAE 27.5 h) for human schedulers — never as an infusion authorization.
3. Twin outputs: predicted delay hours, slot contention, patient-at-risk queue. Twin **cannot** set `qms_release_status`.
4. Production-readiness gap: AuthN/Z is still absent on the local API (`delivery-specification.md` open issues). Close security schemes before any non-synthetic deployment.

**Exit test for 90 days:** a Quality reviewer can open one patient, see identity evidence, ranked exceptions, SOP versions, and a signed HITL decision — and the system still cannot release the batch by itself.

---

## Demo run card (operator)

```text
$env:PYTHONPATH='src'
python -m pytest -q
python -m cgt_orchestrator.cli diagnostics
python -m cgt_orchestrator.cli reconcile --patient-key P-00079
python -m cgt_orchestrator.cli exceptions --patient-key P-00157
uvicorn cgt_orchestrator.api:app --app-dir src --port 8000
```

Then browser: `http://127.0.0.1:8000/dashboard` and `http://127.0.0.1:8000/identity/resolve?patient_key=P-00079`.

**Close:** *“The estate did not fail because it lacked an LLM. It failed because three booleans lied. We fixed the gates, we surfaced identity uncertainty, and we put exception intelligence in front of humans. That is the AI FDE operating model. Repo 3.0 can predict and simulate. It must not release.”*
