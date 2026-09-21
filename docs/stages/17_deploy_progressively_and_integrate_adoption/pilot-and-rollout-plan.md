# Pilot and Rollout Plan

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 17 — Deploy Progressively & Integrate Adoption  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured analysis / specification

## Stage question
How do we shadow-deploy D2 and measure adoption without writing systems of record?

## Why this artifact exists
Part of **Progressive deployment and adoption**. Lifecycle = conditional demo (`20_evaluate_aims_and_decide_lifecycle_state/aims-performance-report.md`).

## Upstream dependency
`16_prepare_operations_recovery_and_regulatory_evidence/operational-runbook.md`; `12_design_security_guardrails_and_supplier_controls/threat-model.md`.

## Evidence to inspect
- `src/cgt_orchestrator/api.py`
- `static/exceptions_dashboard.html`
- `data/reference/baseline_kpis.csv`

## Case challenge
Shadow detector beside `GET /exceptions`. Do not replace QMS. Synthetic (`README.md`).

## Minimum content
- Wave
- Scope
- Shadow vs live
- Adoption telemetry
- Kill switch
- Evidence

## Relevant non-negotiable constraints
- No autonomous release. No non-localhost bind without AuthN/Z.

## Working scaffold
| Wave | Scope | Shadow vs live | Adoption telemetry | Kill switch | Evidence |
|---|---|---|---|---|---|
| 0 Lab | Laptop; seed 42001 | Dashboard shadow; MES/QMS unchanged | `pytest` 25 passed; diagnostics counts stable | Stop uvicorn | `VERIFICATION.md` vs pytest |
| 1 Demo | `/dashboard`; P-00079; P-00157 | Read APIs; ack=receipt | Ack clicks; time-to-first exception | Unmount `/dashboard` | 263 exceptions; identity 0.55 HITL |
| 2 Eng pilot | Persist acks (future) | Still no QMS write | Durable CRITICAL acks | `autonomous_action` must stay `none` | `acknowledge_store.py` |
| 3 Production | **Not authorized** | Needs AuthN/Z + EVAL-005/006 | SLO addendum first | Do not proceed | Stage 15 Partial; `api.py` CORS |

Shadow: SoR unchanged; D2 **shows** MES/QMS=16, slots=9, timelines=9 (`diagnostics.py`). Compare to legacy `/exceptions`.

Adoption (direction only): less `shadow_ops/PatientPriority_MASTER.csv`; no MRN joins; `/legacy/readiness` use should fall.

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Wave 3 blocked | Stage 15; no AuthN | Stage 12/20 | High |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No click logs | Static HTML | Eng | Weak adoption proof | Access log |

## Completion check
- [x] Minimum content complete. Claims cited. Conflicts preserved. Decision rights distinct. No upstream contradiction. N/A unused.

## Handoff
**Stage exit contribution:** Progressive deployment and adoption
