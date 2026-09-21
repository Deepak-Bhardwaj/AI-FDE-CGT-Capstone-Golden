# AIMS Performance Report

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 20 — Evaluate Aims & Decide Lifecycle State  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured narrative + evidence table

## Stage question
Do measured aims justify the next lifecycle state — and which state?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Lifecycle state decision**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use Stage 01 `01_mandate_and_field_immersion/engagement-charter.md`, Stage 15 `15_evaluate_attack_and_independently_assure/red-team-results.md`, Stage 19 `19_prove_value_and_tell_the_decision_story/executive-scqa-and-roadmap.md`, and `data/reference/baseline_kpis.csv`. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `participant/CHALLENGE_BRIEF.md`
- `data/reference/baseline_kpis.csv`
- `VERIFICATION.md`
- `tests/`
- `src/cgt_orchestrator/intelligence/exception_detector.py`
- `CAPABILITY_MAPPING_MATRIX.md`

## Case challenge
Aims are operational truth and governed decision support, not a chatbot (`docs/01_problem_context.md`). Do not invent SLO percentage-point cuts. Recommend a lifecycle state that matches evidence, including residual EVAL-005/006 and missing AuthN/Z.

## Minimum content
- Aim
- Baseline
- Observed
- Gap
- Lifecycle implication

## Relevant non-negotiable constraints
- AI cannot issue or execute clinical, quality-release, chain-of-identity or chain-of-custody decisions or replace QA Release Authority.
- Open deviations, QC holds and incomplete chain-of-identity/custody evidence are hard feasibility constraints until authorized QA release.

## Working scaffold
| Aim | Baseline | Observed | Gap | Lifecycle implication |
|---|---|---|---|---|
| Fewer patient-at-risk **software lies** (QA vs MES, consent, identity) | `product_ready` True on MES/ERP; consent ignored; 3 xfail (`VERIFICATION.md`) | Gates closed; 25 pytest passed; P-00079 HITL 0.55; P-00157 blocked | Fixture still contains 16 MES/QMS conflicts and 5 withdrawn consents (intentional) | Safe to **demo** the gates; not safe to claim clinical risk is gone |
| Reduce manual reconciliation (31.5% journeys) | `baseline_kpis.csv` 31.5% DOWN | 263 typed exceptions vs unranked `/exceptions` deviations | No measured post-change % — NFR-09 forbids inventing it | Instrument in 90-day; do not declare SLO met |
| Cut avoidable delay (186 h / 100 journeys) | Same file | Idempotent slots; no false excursion fail; no false QA-ready | Delay hours not re-measured on 800 journeys | Directionally enabled; **Hold** production KPI claims |
| On-time infusion 78.0% UP | Same file | Consent/site/QA flags fire earlier | Infusion outcomes not simulated | Twin is Stage 21, not current state |
| Explainable identity (17 exceptions / 1,000 DOWN) | Same file | Resolver + 4 MRN collision exceptions; never merge | Human COI execute path not built | **Pilot** identity as read-only |
| Exception age 29.4 h DOWN | Same file | Ranked CRITICAL/HIGH queue; acknowledge receipt | Ack store not durable; age not timestamped from first seen | Partial |
| Local-first essential path | Cloud must not be required | Pytest, CLI, API, dashboard local (`requirements.txt`) | Open CORS / no AuthN/Z (`api.py`) | **Demo-only** network posture |
| Bounded agency | `AGENTS.md` | Every detector row `autonomous_action=none` | Optional LLM not present (correct) | Keep autonomy frozen until Stage 21 |
| TEVV hard gates | EVAL-001–006 | 001–004 + policy xfails **Pass**; 005–006 **Partial** | No document-injection or QMS-outage contract test | Cannot enter **Production** |
| Traceability 82.4% UP | KPI file | Source-qualified statuses preserved; challenge rows not overwritten | Cross-system write audit still thin | Reuse D2; do not replace SoR |

### Lifecycle state recommendation

| State | Meaning | Decision |
|---|---|---|
| Retire | Shut the increment | **No** — value of D2 is evidenced |
| Hold / lab only | Synthetic, local | **Current bound** for the API as exposed |
| **Conditional executive demo / engineering pilot** | Trainer demo + pytest as control plane | **SELECTED** |
| Limited production | Named sites, AuthN/Z, EVAL-005/006 tests | **Not yet** |
| Scale globally | Charter outcome | **No** — 90-day moonshot only |

**Decision:** **Conditional engineering pilot / executive demo.** Promote **deterministic gates + POC 1 + POC 2 HITL** as the reusable control plane. Do **not** change lifecycle to production: AuthN/Z absent, EVAL-005/006 incomplete, KPIs direction-only, estate synthetic (`README.md`).

**Exit conditions to Limited production (future):** executable EVAL-005/006; OpenAPI securitySchemes; durable HITL audit; signed SLO addendum; independent review.

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Software-gate aims met | `14_engineer/technical-defect-resolution-report.md`; 25 passed | Stage 14/15 | High |
| Operating KPI aims not quantitatively closed | `data/reference/baseline_kpis.csv` target_direction only | Stage 01/13 open issue | High that we must not claim % cuts |
| Selected lifecycle is demo/pilot not scale | Stage 15 residual + `api.py` CORS | This stage | Judgement, evidence-backed |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No named executive sponsor | `participant/CHALLENGE_BRIEF.md` | Engagement lead | Lifecycle owner is role-based | Sponsor artifact |
| AIMS here = engagement aims, not a certified AI management system | Capstone scope | Assurance | Do not cite ISO/GxP certification | `README.md` fictional |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Lifecycle state decision

Stage 21 may expand Repo 3.0 only inside this lifecycle bound: predict and simulate; do not release.
