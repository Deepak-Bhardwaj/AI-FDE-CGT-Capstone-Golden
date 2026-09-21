# AI Suitability Assessment

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 04 — Triage Regulation & Qualify Use Case  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured analysis / specification

## Stage question
Should AI be used at all, and under what impact/regulatory constraints?

## Why this artifact exists
Part of **Approved and justified use case** (`README.md` synthetic).

## Upstream dependency
`03_frame_problem_root_cause_and_value/scqa-problem-frame.md`.

## Evidence to inspect
- `docs/sops/SOP-QA-014-v4.md`; `AGENTS.md`; `status_rules.py`

## Case challenge
Justify AI vs non-AI.

## Minimum content
Suitability, use-case card, go/no-go.

## Relevant non-negotiable constraints
- AI cannot execute QA-release, COI or COC (`AGENTS.md`).

## Working scaffold
| Task | AI contribution | Deterministic alternative | Data/eval readiness | Failure tolerance | Human dependency | Decision |
|---|---|---|---|---|---|---|
| QA release | None | `product_ready()` / `QmsReleaseState` | SOP-QA-014-v4; EVAL-005 | Zero | QA Authority | **NO-GO AI** |
| Identity merge | None | `patient_resolver.py` | EVAL-002 P-00079 | Zero silent merge | Human COI | **NO-GO write** |
| Exception rank (POC 2) | Observe/recommend | `diagnostics.py` | 263 rows; HITL pytest | Recommend-only | Ack ≠ SoR | **GO correlator** |

| Actor | Job-to-be-done | Trigger | Inputs | AI responsibility | Human responsibility | Output | Value/risk |
|---|---|---|---|---|---|---|---|
| QA | See blockers pre-infusion | MES≠QMS; WITHDRAWN | `exception_detector.py` | Rank; `autonomous_action=none` | Release/COI | `/api/exceptions/active` | Risk: ack as release |

| Gate | Go criterion | No-go/kill criterion | Evidence | Owner | Reassessment trigger |
|---|---|---|---|---|---|
| Authority | No QMS write | Auto-release; ignore consent | `api.py`; EVAL-004 | QA | New PATCH |
| Identity / local-first | Conflict surfaced; pytest without cloud | `canonical_dob`; LLM required | `tests/test_patient_reconciliation.py`; `VERIFICATION.md` | COI/Eng | Resolver write; adapter on |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| POC 2 GO as correlator | `src/cgt_orchestrator/intelligence/exception_detector.py` | Stage 08 D2 | High on fixture |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| Not a GxP filing | `README.md` | Assurance | No legal clearance | Counsel if real |

## Completion check
- [x] Complete; cited; conflicts kept; rights distinct.

## Handoff
**Stage exit contribution:** Approved and justified use case
