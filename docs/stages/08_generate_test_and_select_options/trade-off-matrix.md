# Weighted Trade-Off Matrix

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 08 — Generate, Test & Select Options  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured table / register

## Stage question
Which solution survives evidence, alternatives and trade-offs?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Approved solution and trade-offs**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use the completed Stage 07 artifact `07_define_evaluations_impacts_and_risks/evaluation-strategy.md` and Stage 13 `13_approve_adrs_and_delivery_specification/delivery-specification.md`. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `evals/cases.csv`
- `scenarios/inject_catalog.csv`
- `data/raw/batches.csv`
- `docs/04_target_capabilities_not_prescribed_solutions.md`
- `src/cgt_orchestrator/legacy/status_rules.py`
- `src/cgt_orchestrator/intelligence/exception_detector.py`

## Case challenge
Compare at least one non-AI/deterministic option and more than one AI architecture option. Preserve rejected options and why they lost.

## Minimum content
- Criterion
- Weight
- Option score
- Evidence
- Sensitivity
- Comment

## Relevant non-negotiable constraints
- AI cannot issue or execute clinical, quality-release, chain-of-identity or chain-of-custody decisions or replace QA Release Authority.
- Open deviations, QC holds and incomplete chain-of-identity/custody evidence are hard feasibility constraints until authorized QA release.

## Working scaffold

**Options scored 1–5 (5 = best).** Weighted score = Σ (weight × score) / 100.

| ID | Option | Class |
|---|---|---|
| D1 | Deterministic gates only (`status_rules`, `slot_service`, diagnostics CLI) | Non-AI |
| **D2 (selected)** | **D1 + POC 1 identity resolver + POC 2 exception intelligence (HITL, no LLM)** | Deterministic + bounded correlator |
| A1 | LLM/RAG over SOPs + `shadow_ops/` as the operator interface | Generative AI |
| A2 | Multi-agent mesh with write tools (auto-release, auto-merge, auto-rebook) | Agentic write autonomy |
| A3 | Knowledge graph / digital twin as the new system of record | Prescribed platform |

| Criterion | Weight | D1 | D2 | A1 | A2 | A3 | Evidence | Sensitivity | Comment |
|---|---|---|---|---|---|---|---|---|---|
| Authority / HITL (QA, COI, COC stay human) | 25 | 5 | 5 | 2 | 1 | 2 | `AGENTS.md`; EVAL-004/006; `autonomous_action=none` in `exception_detector.py` | If weight drops, A1 still fails EVAL-006 | Hard constraint, not a preference |
| Local-first / no cloud for essential path | 15 | 5 | 5 | 1 | 2 | 2 | `AGENTS.md`; `VERIFICATION.md` LLM disabled; `requirements.txt` FastAPI/pytest only | A1 collapses if cloud is forbidden | NFR-01 |
| Explainable identity (no fabricated merge) | 15 | 2 | 5 | 2 | 1 | 3 | `patient_resolver.py`; EVAL-002 P-00079; duplicate MRN `MRN-389336` | D1 lacks FR-02 | SQLite is not identity SoT |
| Exception ranking with evidence (FR-06) | 15 | 2 | 5 | 3 | 3 | 3 | Detector 263 rows; MES/QMS n=16 matches `diagnostics.py` | D1 only emits counts | `/exceptions` unranked deviations are insufficient |
| Testability / TEVV on this fixture | 15 | 5 | 5 | 2 | 1 | 2 | 25 pytest passed; converted xfails in `test_legacy_expected_failures.py` | A2 untestable without SoR writes | Hard gates over average LLM score |
| Time-to-value on brownfield (no rewrite) | 10 | 4 | 5 | 2 | 1 | 1 | `14_engineer/technical-defect-resolution-report.md`; did not clean `data/raw/` | A3 is a platform program | Prefer reversible increments |
| Moonshot optionality (later agents/twin) | 5 | 2 | 4 | 3 | 4 | 4 | `docs/04_target_capabilities_not_prescribed_solutions.md` | Low weight on purpose | D2 is the substrate agents may *read* |
| **Weighted total** | **100** | **3.85** | **4.95** | **2.05** | **1.55** | **2.30** | | | **Select D2** |

**Rejected and why they lost**

| Option | Why it lost |
|---|---|
| D1 | Closes FR-04/05/07/08 but not FR-02/FR-06; operators stay in `shadow_ops/PatientPriority_MASTER.csv` |
| A1 | Cloud-coupled; untrusted notes become instructions (EVAL-006); cannot be the essential path |
| A2 | Violates non-negotiable: would auto-release / merge / rebook; INJ-006 already showed non-idempotent writes are harmful |
| A3 | Prescribes a KG/twin as SoR; `docs/04_target_capabilities_not_prescribed_solutions.md` forbids that as the required solution |

**Accepted trade-off of D2:** no generative summarization in this increment; QA-release forecast MAE (27.5 h in `data/reference/baseline_kpis.csv`) is **not** improved yet. That is Stage 21 / Repo 3.0, not a reason to pick A1.

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Selected D2 is what the repo now runs | `src/cgt_orchestrator/reconciliation/patient_resolver.py`; `src/cgt_orchestrator/intelligence/exception_detector.py`; `src/cgt_orchestrator/api.py` | Stage 13 FR-02/06; Stage 14 | High |
| 16 MES vs QMS conflicts remain as challenge data | `data/raw/batches.csv`; diagnostics `mes_qms_conflict_count=16` | Stage 02 | High — not “cleaned” |
| Weights are an engagement judgement | This matrix | Stage 08 | Assumption — trainer may re-weight; D2 still wins if authority stays ≥20 |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| Optional LLM adapter remains off | Local-first | Architecture | Stage 11 agents may summarize *cited* evidence only | Adapter flag default false |
| A2 may be revisited as observe-only multi-agent | Stage 21 90-day | Product | Must not gain write tools | Stage 11 autonomy ADR |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Approved solution and trade-offs

Do not advance to Stage 09 until the Stage 08 exit gate is defensible.
