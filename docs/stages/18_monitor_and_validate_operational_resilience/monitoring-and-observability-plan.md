# Monitoring and Observability Plan

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 18 — Monitor & Validate Operational Resilience  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured analysis / specification

## Stage question
What SLIs/SLOs, drift checks and alerts prove D2 still fails safe?

## Why this artifact exists
Part of **Operational resilience monitoring**. Targets are direction-only (`data/reference/baseline_kpis.csv`).

## Upstream dependency
`07_define_evaluations_impacts_and_risks/evaluation-strategy.md`.

## Evidence to inspect
- `diagnostics.py`; `exception_detector.py`; `evals/cases.csv`

## Case challenge
Monitor counts/gates, not chat scores.

## Minimum content
Signal, SLI/SLO, alert, drift, owner, evidence.

## Relevant non-negotiable constraints
- Open deviations block release. API down → CLI.

## Working scaffold
| Signal | SLI / SLO | Alert | Drift / resilience | Owner | Evidence |
|---|---|---|---|---|---|
| Integrity | `patient_count==800` | ≠ `data/manifest.json` | Seed drift | Data | `diagnostics.py` |
| MES/QMS | Detector n=**16** | ≠ diagnostics | Logic vs silent clean | QA | `exception_detector.py` |
| Timelines | n=**9** | Drop to 0 w/o spec | Challenge-data wipe | Logistics | EVAL-003 |
| Consent / MRN | P-00157 HITL; 2 MRNs / 4 exceptions | `patient_ready` True if WITHDRAWN; merge on collision | Authority/identity drift | Clinical/COI | EVAL-004; `patient_resolver.py` |
| Autonomy / pytest | 100% `autonomous_action=none`; 25 passed | Any other; fail | Agent-write / gate regression | Assurance/Eng | `tests/test_exception_intelligence.py` |
| Health / ack | `/health` synthetic; exception still listed after ack | Non-200; QMS column changes | Restart/CLI; SoR leak | Ops/QA | `api.py`; `acknowledge_store.py` |
| KPI / outage | 31.5% recon DOWN (direction); Hold if QMS down | Invented %; auto-ready | EVAL-005 **gap** | Product/QA | `baseline_kpis.csv`; Stage 15 |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Count equality is the challenge-signal SLO | diagnostics vs detector tests | Stage 07/15 | Fixture only; no APM |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No metrics backend | Demo | Eng | Alerts=pytest+CLI | Exporter later |

## Completion check
- [x] Minimum content complete. Claims cited. Conflicts preserved. Decision rights distinct. No upstream contradiction. N/A unused.

## Handoff
**Stage exit contribution:** Operational resilience monitoring
