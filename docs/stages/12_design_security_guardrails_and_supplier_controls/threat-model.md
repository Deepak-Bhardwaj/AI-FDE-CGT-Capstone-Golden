# Threat Model

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 12 — Design Security Guardrails & Supplier Controls  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured table / register

## Stage question
What threats, trust boundaries and supplier controls keep HITL intact?

## Why this artifact exists
Part of **Security, guardrails and supplier controls**.

## Upstream dependency
`11_design_agentic_and_multi_agent_orchestration/agent-bounded-autonomy.md`; `docs/06_security_privacy_assurance.md`.

## Evidence to inspect
- `src/cgt_orchestrator/api.py`; `acknowledge_store.py`; `evals/cases.csv`; `AGENTS.md`

## Case challenge
Map OWASP-class risks. Documents are data, not instructions (EVAL-006).

## Minimum content
Threat, asset, vector, control, HITL/residual, evidence.

## Relevant non-negotiable constraints
- No autonomous QA/COI/COC. Essential path has no cloud supplier.

## Working scaffold
| Threat (OWASP-aligned) | Asset | Vector | Control | HITL / residual | Evidence |
|---|---|---|---|---|---|
| LLM01 injection | QA release | “Ignore rules / mark released” | `shadow_ops/` not commands; ack≠SoR | EVAL-006 pytest **Partial** | `evals/cases.csv` |
| A01 broken access | API | Unauth FastAPI; CORS `*` | Localhost only | **Kill** if exposed | `api.py` |
| Insecure design / agency | False ready; batch state | `/legacy/readiness`; agent writes | QMS gate; `autonomous_action=none` | Quarantine; ack memory | `status_rules.py`; `exception_detector.py` |
| Overreliance / supply chain | Operator; PyPI | Ack as close; deps | Banner; pin `requirements.txt` | Training; restricted-key=0 | `exceptions_dashboard.html`; `VERIFICATION.md` |
| Identity merge / replay | COI; slots | Join MRN; timeout | Resolver refuses; idempotent `reserve` | Human COI; INJ-006 | `patient_resolver.py`; `slot_service.py` |

**Trust boundaries:** CSV vs SQLite; MES vs QMS; shadow vs SoR; human QA vs gates; LLM (off) vs detector.

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| No QMS write route | `api.py` | Stage 11 | High |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| AuthN/Z missing | Demo | Security | Stage 17 stays laptop | OpenAPI schemes |

## Completion check
- [x] Minimum content complete. Claims cited. Conflicts preserved. Decision rights distinct. No upstream contradiction. N/A unused.

## Handoff
**Stage exit contribution:** Security, guardrails and supplier controls
