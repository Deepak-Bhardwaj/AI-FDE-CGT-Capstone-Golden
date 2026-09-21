# 90-Day Roadmap (Repo 3.0)

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 21 — Retire & Capture Reusable IP  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured table / register

## Stage question
What do we retire, what reusable IP do we keep, and what may Repo 3.0 become in 90 days without violating authority bounds?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Reusable IP and next-generation roadmap**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use Stage 08 `08_generate_test_and_select_options/trade-off-matrix.md` (D2), Stage 20 `20_evaluate_aims_and_decide_lifecycle_state/aims-performance-report.md` (conditional pilot), and Stage 19 `19_prove_value_and_tell_the_decision_story/executive-scqa-and-roadmap.md`. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `docs/04_target_capabilities_not_prescribed_solutions.md`
- `scenarios/inject_catalog.csv`
- `evals/cases.csv`
- `src/cgt_orchestrator/legacy/status_rules.py`
- `src/cgt_orchestrator/intelligence/exception_detector.py`
- `src/cgt_orchestrator/reconciliation/patient_resolver.py`
- `data/raw/cryogenic_telemetry.csv`

## Case challenge
Capture IP from D2. Retire unsafe surfaces. Expand toward predictive logistics, bounded multi-agent, and a vein-to-vein **simulation** twin — capabilities, not a prescribed KG/RAG/agent mesh (`docs/04_target_capabilities_not_prescribed_solutions.md`). Lifecycle remains conditional pilot (Stage 20).

## Minimum content
- Item
- Retire / reuse / create
- 90-day action
- Owner
- Exit evidence

## Relevant non-negotiable constraints
- AI cannot issue or execute clinical, quality-release, chain-of-identity or chain-of-custody decisions or replace QA Release Authority.
- Cloud/LLM availability must not be required for essential patient-to-batch orchestration operations.
- Duplicate/replayed events must be handled idempotently and with temporal provenance.

## Working scaffold

### Reusable IP to keep (do not rewrite)
| Item | Retire / reuse / create | 90-day action | Owner | Exit evidence |
|---|---|---|---|---|
| `QmsReleaseState` / `ConsentState` / `product_ready` | **Reuse** | Freeze as hard gates; any new feature must call them | Engineering | pytest xfail triad stays green |
| `SlotService` idempotency | **Reuse** | Promote to specified `POST /slots/reservations` with `Idempotency-Key` | Engineering | INJ-006 contract on HTTP |
| `PatientResolver` | **Reuse** | Keep CSV evidence; never switch identity SoT to SQLite | COI + Eng | EVAL-002 still fails a silent merge |
| `exception_detector` + HITL ack | **Reuse** | Persist acks; add first-seen timestamp for exception age KPI | Engineering | Durable audit + `open_exception_mean_age_hours` instrumented |
| TEVV pack EVAL-001–006 + INJ-001–010 | **Reuse** | Make 005/006 executable | Assurance | New pytest names |
| Challenge data in `data/raw/` | **Reuse as signals** | Do not globally clean 16 MES/QMS rows, 9 timelines, P-00079 DOBs | Data steward | Diagnostics counts stable on seed 42001 |
| Stage artifacts 01/02/05/13/14 | **Reuse** | Cite in demo; do not silently redefine SOP versions | FDE lead | SOP-QA-014-v4 / SOP-LOG-007-v7 |

### Retire or quarantine
| Item | Retire / reuse / create | 90-day action | Owner | Exit evidence |
|---|---|---|---|---|
| `/legacy/readiness` as a decision surface | **Quarantine → retire** | Remove after FR-04/05 consumers gone; keep warning until then | Engineering | Delivery spec API table |
| OR-logic MES/ERP “ready” | **Retired** (code) | Guardrail test remains | Engineering | `test_product_not_ready_until_qa_released` |
| SOP-LOG-007 v6 point auto-fail | **Retired** (code) | Keep v6 file as superseded evidence | Quality | `docs/sops/SOP-LOG-007-v6.md` Status: Superseded |
| Unauthenticated non-localhost bind | **Retire for any non-demo** | Add AuthN/Z or bind 127.0.0.1 only | Security | OpenAPI securitySchemes |
| Write-capable agent mesh (option A2) | **Do not create** | Observe-only agents may wrap D2 tools | Architecture | Stage 11 ADR |

### Repo 3.0 — 90 days (moonshot expansion)
| Item | Retire / reuse / create | 90-day action | Owner | Exit evidence |
|---|---|---|---|---|
| **Days 0–30 Predictive logistics** | Create | Typed telemetry pack from `data/raw/cryogenic_telemetry.csv`; INJ-002 duration/quality/cumulative; EVAL-003 source inquiry; INJ-008 courier notes as data | Logistics + Quality | Review pack; still no auto-fail / auto-reroute |
| **Days 0–30 EVAL-005/006 harness** | Create | QMS-down → HOLD payload; ingest `shadow_ops/` note asserting no release | Assurance | pytest EVAL-005/006 |
| **Days 31–60 Bounded multi-agent** | Create (optional, LLM off by default) | Identity correlator, exception ranker, release-pack assembler **recommend only**; slot tool deterministic | Architecture | Agents call existing Python tools; EVAL-004 halt still holds |
| **Days 31–60 Release-review API** | Create | Specified `POST /recommendations/release-review` — cannot set `qms_release_status` | QA + Eng | NFR-08; SOP-QA-014-v4 on payload |
| **Days 61–90 Vein-to-vein twin** | Create as **simulation**, not SoR | Replay INJ-001–010 on 800-patient fixture; forecast QA-release as uncertainty band (baseline MAE 27.5 h in `data/reference/baseline_kpis.csv`) | Product + Eng | Twin cannot write QMS; infusion not authorized by forecast |
| KPI SLO addendum | Create | Product owner signs numeric targets (31.5% / 186 h / 78%) | Product | Closes NFR-09 open issue |
| COI proposal API | Create | Specified `POST /identity/conflicts/{id}/proposals` — propose only | COI steward | Approve → execute → audit still human |

**Hard stop for all 90 days:** no autonomous QA release, identity merge, or chain-of-custody disposition. Cloud must remain optional. Challenge rows stay.

**90-day exit test:** a Quality reviewer opens one patient, sees identity evidence, ranked exceptions, SOP + rule versions, and a signed HITL decision — and the system still cannot release the batch by itself (Stage 19 close line).

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| D2 is the IP core | `patient_resolver.py`; `exception_detector.py`; `status_rules.py` | Stage 08/14 | High |
| Twin is capability not a mandated graph | `docs/04_target_capabilities_not_prescribed_solutions.md` | Stage 21 challenge | Binding |
| Lifecycle bound is pilot | Stage 20 recommendation | Stage 20 | Judgement |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| 90-day calendar assumes local synthetic estate only | Not a real network | Engagement lead | Dates are planning, not a vendor commitment | Charter boundary |
| LLM summarization of *cited* evidence may be added off-by-default | Local-first | Architecture | Must fail closed to CLI if adapter missing | Adapter flag |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Reusable IP and next-generation roadmap

Repo 3.0 can predict and simulate. It must not release.
