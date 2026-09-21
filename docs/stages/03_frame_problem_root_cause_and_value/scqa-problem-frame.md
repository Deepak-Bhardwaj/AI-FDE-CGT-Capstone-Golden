# SCQA Problem Frame

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 03 — Frame Problem, Root Cause & Value  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured narrative + evidence table

## Stage question
What evidence proves the problem, its causes and its value?

## Why this artifact exists
Part of **Evidence-backed problem and measurable baseline**. Do not silently redefine upstream facts.

## Upstream dependency
`02_discover_process_and_architecture/brownfield-assessment.md`.

## Evidence to inspect
- `data/reference/baseline_kpis.csv`; `data/raw/batches.csv`; `shadow_ops/PatientPriority_MASTER.csv`

## Case challenge
Use `data/raw/`, `evals/`, `scenarios/`. Do not invent statistics.

## Minimum content
Situation, Complication, Question, Answer, Evidence, Assumption — plus root-cause table.

## Relevant non-negotiable constraints
- AI cannot replace QA Release Authority (`AGENTS.md`). Open deviations/QC holds/incomplete COI block release.

## Working scaffold
| Situation | Complication | Question | Answer hypothesis | Evidence | Assumption |
|---|---|---|---|---|---|
| 800 patients, seed 42001 (`data/manifest.json`). Baseline: 31.5% manual recon; 186 delay h/100; 78.0% on-time (`data/reference/baseline_kpis.csv`). | 16 MES≠QMS (`diagnostics.py`); `/legacy/readiness` hides uncertainty (`api.py`); 3 xfails (`tests/test_legacy_expected_failures.py`); shadow priority (`shadow_ops/PatientPriority_MASTER.csv`). | How cut patient-at-risk while scaling, without autonomous QA/COI/COC? | Deterministic gates + identity evidence + HITL ranking. | `14_engineer/technical-defect-resolution-report.md`; `exception_detector.py`. | KPI direction-only. |

| Cause/hypothesis | Evidence for | Evidence against | Controllable? | Root/symptom | Test or next evidence |
|---|---|---|---|---|---|
| Homonymous RELEASED + OR-logic | Pre-fix `status_rules.py`; 16 rows `data/raw/batches.csv` | Some QMS RELEASED true | Yes | **Root** | `test_product_not_ready_until_qa_released` |
| SQLite as identity SoT | P-00079 CRM DOB `1959-12-23`; `MRN-389336` | P-00001 aligned | Yes (resolver, not wipe) | **Root** | `tests/test_patient_reconciliation.py` |
| Email as SoR | `shadow_ops/ManufacturingSlots_FINAL_v7.csv` OVERRIDE | P-00001 happy path | Partial | Symptom | `GET /api/exceptions/active` |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| 31.5%/186 h synthetic | `data/reference/baseline_kpis.csv` | Stage 01 | High; not production |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No numeric SLO | `target_direction` only | Product | Do not invent % | SLO addendum |

## Completion check
- [x] Minimum content complete. Claims cited. Conflicts preserved. Decision rights distinct. No upstream contradiction. N/A unused.

## Handoff
**Stage exit contribution:** Evidence-backed problem and measurable baseline
