# Agent Bounded Autonomy

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 11 — Agentic & Multi-Agent Orchestration  
**Participant status:** `COMPLETED`  
**Deliverable form:** ADR / decision record

## Stage question
Is autonomy justified, bounded, permissioned, interruptible and testable?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Approved, bounded and testable agentic architecture**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use Stage 08 `08_generate_test_and_select_options/trade-off-matrix.md` (selected D2) and Stage 13 `13_approve_adrs_and_delivery_specification/delivery-specification.md` Agent / HITL table. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `AGENTS.md`
- `src/cgt_orchestrator/legacy/status_rules.py`
- `src/cgt_orchestrator/intelligence/exception_detector.py`
- `src/cgt_orchestrator/intelligence/acknowledge_store.py`
- `src/cgt_orchestrator/reconciliation/patient_resolver.py`
- `evals/cases.csv`
- `docs/sops/SOP-QA-014-v4.md`

## Case challenge
The correct result may be NO AGENT. Complete agent suitability first. If autonomy is not justified, complete remaining Stage 11 artifacts as NOT APPLICABLE with rationale, approving role and downstream consequence.

## Minimum content
- Capability
- Autonomy level
- Allowed actions
- Prohibited actions
- Approval boundary
- Revocation/fallback

## Relevant non-negotiable constraints
- Open deviations, QC holds and incomplete chain-of-identity/custody evidence are hard feasibility constraints until authorized QA release.
- Cloud/LLM availability must not be required for essential patient-to-batch orchestration operations.
- Duplicate/replayed events must be handled idempotently and with temporal provenance.

## Working scaffold
### Context / decision drivers
Selected solution D2 is **deterministic correlation + HITL**, not a write-capable agent mesh (`08_generate_test_and_select_options/trade-off-matrix.md`). Autonomy is justified only for observe / correlate / recommend (`.cursor/rules/cgt-fde.mdc` item 4). Consequential QA / COI / COC is **NO AGENT**.

### Options considered
| Option | Evidence | Advantages | Disadvantages / risks |
|---|---|---|---|
| No agent (D1 only) | `status_rules.py`; `diagnostics.py` | Safest writes | FR-06 unranked; operators stay in `shadow_ops/` |
| **Bounded correlator (D2, selected)** | `exception_detector.py`; `patient_resolver.py` | Evidence + HITL; local-first | No generative narrative in-increment |
| Write-capable agents | Rejected A2 | Speed | Violates EVAL-004/006; INJ-006 |

### Decision
Approve **observe / correlate / recommend** for exception ranking and identity evidence. Approve **deterministic tool** for idempotent slot reserve. **None** for release, COI execute, consent override, excursion fail. Optional LLM remains off (`AGENTS.md`).

### Consequences and reversal trigger
Revoke correlator display if any path writes `qms_release_status` or merges `patient_key`. Fallback: `python -m cgt_orchestrator.cli diagnostics` and pytest gates.

### Capability × autonomy
| Capability | Autonomy level | Allowed actions | Prohibited actions | Approval boundary | Revocation/fallback |
|---|---|---|---|---|---|
| Identity resolve (POC 1) | Observe | Read three CSVs; emit evidence, confidence, HITL | Fabricate linkage; write CRM/QMS; emit `canonical_dob` | Human COI (`docs/06_security_privacy_assurance.md`) | Leave conflict open; CLI `reconcile` |
| Exception rank (POC 2) | Observe / recommend | Detect MES/QMS, slots, timelines, consent, deviations, sites, MRNs | Close deviations; release batch; auto-rebook | Human QA or COI | CLI `exceptions`; detector still read-only |
| HITL acknowledge | Interrupt / receipt | Record actor + note in process memory | Change patient, batch, shipment, QMS | Operator / QA | `acknowledge_store.reset`; SoR unchanged |
| `product_ready` / `patient_ready` | Deterministic gate | Return False on QMS not RELEASED / consent WITHDRAWN | Authorize infusion or QA release | QA + Clinical | `/legacy/readiness` warning string |
| Excursion | Recommend review | Flag `temp_c > -120` | Auto-fail shipment (SOP-LOG-007 v7) | Quality disposition | Hold shipment |
| Slot reserve | Deterministic tool | Idempotent `reserve` (`slot_service.py`) | Cancel MES; retry without key (INJ-006) | Scheduler + MES for cancels | Same `reservation_id` on replay |
| Release / COI execute | **None** | Assemble evidence (future FR) | Set QMS status; obey courier “mark released” (EVAL-006) | QA Release Authority | HOLD (EVAL-005) |

### HITL matrix
| Action/decision | Required human role | Approval evidence | Override reason | Escalation | Audit trace |
|---|---|---|---|---|---|
| Identity conflict (P-00079, duplicate MRN) | Chain-of-identity | Resolver `conflicts[]`, confidence 0.55 / 0.0 | Never auto-merge | Clinical + identity steward | `rule_version=patient-resolver-v1`; `GET /identity/resolve` |
| MES RELEASED / QMS not (n=16) | QA | Exception `MES_RELEASED_QMS_NOT_RELEASED`; SOP-QA-014-v4 | Cannot treat MES as release | QA Release Authority | `exception-detector-v1`; batch_id in evidence |
| Consent WITHDRAWN in-flight (P-00157) | Clinical + QA | `CONSENT_BLOCKING_IN_FLIGHT_JOURNEY`; EVAL-004 | No downstream continuation | Halt manufacturing/release/infusion recs | `/api/patients/P-00157/journey` blockers |
| Impossible timeline (n=9) | Logistics + Quality | `IMPOSSIBLE_SHIPMENT_TIMELINE`; EVAL-003 | Do not invent corrected timestamps | Quality | `occurred_at` vs `recorded_at` (`data/raw/events.jsonl`) |
| Open deviation (135 OPEN+INVESTIGATING) | QA | `OPEN_QUALITY_DEVIATION` | Cannot auto-close | QA | `data/raw/deviations.csv` |
| Dashboard Acknowledge | Demo operator / QA | POST acknowledge | Receipt only | None — not a disposition | `effect_on_systems_of_record=none` |
| QA product release | QA (human) | QC + closed blocking deviations | System must not override | Hold / do not ship | No write endpoint exists |

### Tool contracts
| Tool/action | Purpose | Read/write | Required role | Precondition | Side effect | Approval |
|---|---|---|---|---|---|---|
| `GET /identity/resolve` | POC 1 evidence pack | Read | Operator | One of patient_key / crm_id / clinical_id / mrn | None | None (read) |
| `GET /api/exceptions/active` | Ranked contradictions | Read | Operator | Local SQLite + CSVs | None | None (read) |
| `GET /api/patients/{id}/journey` | Journey + blockers | Read | Operator | Known `patient_key` | None | None (read) |
| `POST /api/exceptions/{id}/acknowledge` | HITL receipt | Write **memory only** | Named actor | Exception id exists | In-process ack dict | Human click; not QA release |
| `SlotService.reserve` | Idempotent hold | Write in-memory | Scheduler tool | `patient_key`, `site_id` | One reservation per key | Not QA |
| `product_ready` / `patient_ready` | Deterministic stop | Read calc | Any caller | Batch/consent records | None | Must not be used as clinical auth (`api.py` warning) |
| `POST /recommendations/release-review` | Specified, **not built** | Read calc | QA | QMS reachable or HOLD | None if built | QA — N/A until implemented |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Every detector row is HITL + no autonomous action | `tests/test_exception_intelligence.py`; 263 rows seed 42001 | Stage 08 D2 | High on fixture |
| Acknowledge does not write SoR | `acknowledge_store.py` | Stage 13 HITL | High — in-memory only; lost on process restart |
| Write-capable agent is rejected | EVAL-004/006; trade-off A2 | Stage 07/08 | Binding |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No AuthN/Z on FastAPI | `api.py` CORS `allow_origins=["*"]` | Security | Demo-only; not production | OpenAPI securitySchemes |
| Multi-agent topology deferred to Stage 21 days 31–60 | Optional LLM off | Architecture | Do not imply a running agent mesh | 90-day roadmap |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Approved, bounded and testable agentic architecture

This contributes to the final Stage 11 architecture defence.
