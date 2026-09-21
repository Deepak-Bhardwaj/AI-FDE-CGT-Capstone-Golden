# Engagement Charter

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 01 — Mandate & Field Immersion  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured narrative + evidence table

## Stage question
Why are we here, what outcome matters, who owns it, and who is affected?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Approved mandate and operating context**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use the Capstone repository (`README.md`, `participant/CHALLENGE_BRIEF.md`) and supplied evidence. No solution architecture is an input to Stage 01.

## Evidence to inspect
- `data/manifest.json`
- `docs/01_problem_context.md`
- `AGENTS.md`
- `docs/03_architecture_current_state.md`

## Case challenge
Stay in the field problem and ownership space. Do not propose a model, graph database, agent or UI in this artifact.

## Minimum content
- Problem/opportunity
- Business outcome
- Engagement boundaries
- Decision rights
- Working assumptions
- Evidence plan

## Relevant non-negotiable constraints
- AI cannot issue or execute clinical, quality-release, chain-of-identity or chain-of-custody decisions or replace QA Release Authority.
- Open deviations, QC holds and incomplete chain-of-identity/custody evidence are hard feasibility constraints until authorized QA release.

## Working scaffold
| Problem/opportunity | Business outcome | Engagement boundaries | Decision rights | Working assumptions | Evidence plan |
|---|---|---|---|---|---|
| Autologous journeys fail as *operational truth* problems, not isolated bugs: CRM can show ready while the scheduler is only provisional, QMS holds an open deviation, logistics has not confirmed return, and the treatment center has already scheduled conditioning (`docs/01_problem_context.md`). | Reduce patient-at-risk cases, manual coordination and avoidable delays while scaling globally (`participant/CHALLENGE_BRIEF.md`). Primary baseline: 31.5% of journeys require manual reconciliation; 186 avoidable delay hours per 100 journeys; 78.0% on-time infusion probability (`data/reference/baseline_kpis.csv`). | In: forensic discovery of the synthetic brownfield estate (800 patients, 800 batches, 188 deviations, 24 treatment centers, 6 manufacturing sites; `data/manifest.json`). Out: validated GxP/clinical/regulatory operation; this repo is fictional/synthetic (`README.md`). Out: silent global “repair” of seeded contradictions (`AGENTS.md`). | Consequential clinical, quality-release, chain-of-identity and chain-of-custody decisions remain human (`AGENTS.md`). Manufacturing complete is not product release (`docs/sops/SOP-QA-014-v4.md`). | Latest timestamp is not latest real-world event; QC complete, QA released, product ready and infusion ready must not be collapsed (`AGENTS.md`, `.cursor/rules/cgt-fde.mdc`). Baseline must remain locally runnable without cloud credentials (`AGENTS.md`). | Run `python -m cgt_orchestrator.cli diagnostics`; inspect `data/raw/`, `shadow_ops/`, `src/cgt_orchestrator/legacy/`, `tests/`, `docs/sops/`, `evals/cases.csv`, `scenarios/inject_catalog.csv` (`README.md`, `participant/DISCOVERY_CHECKLIST.md`). |
| Manual reconciliation and shadow operations sit beside systems of record: planner spreadsheet `shadow_ops/PatientPriority_MASTER.csv` (priority/reason/updated_by including `unknown`); slot overrides with `EMAIL OVERRIDE - moved Thu` (`shadow_ops/ManufacturingSlots_FINAL_v7.csv` SLOT-00001); 31 open courier escalations (`shadow_ops/CourierEscalations.csv`); 12.7 manual status updates per journey (`data/reference/baseline_kpis.csv`). | Cut manual status updates and exception age (open-exception mean age 29.4 hours; `data/reference/baseline_kpis.csv`) by making system-of-record conflicts visible rather than email-resolved. | In: document shadow vs system evidence without deleting either. Out: treating `shadow_ops/` as canonical over MES/QMS/CRM (`docs/05_data_map.md`, `AGENTS.md`). | Scheduling may provisionally reserve capacity before reimbursement, but treatment-center and quality gating must be revalidated before downstream clinical milestones (`docs/sops/SOP-SCHED-003-v2.md`, Status: Draft). | Shadow files are evidence of workarounds, not a second master to silently merge (`docs/05_data_map.md`). | Compare `data/raw/manufacturing_slots.csv` vs `shadow_ops/ManufacturingSlots_FINAL_v7.csv`; sample `shadow_ops/emails/`; retain provenance. |
| Identity and lineage are multi-keyed and already conflicted: patients carry `patient_key`, `crm_patient_id`, `clinical_subject_id`, `mrn` (`data/raw/patients.csv`); diagnostics report `duplicate_mrn_count=2` (`VERIFICATION.md`); EVAL-002 P-00079 CRM DOB `1959-12-23` vs clinical/orchestration DOB `1959-12-22` (`data/raw/crm_patient_export.csv`, `data/raw/clinical_patient_export.csv`, `evals/cases.csv`). | Explainable patient/material/batch identity resolution and end-to-end provenance (`docs/04_target_capabilities_not_prescribed_solutions.md`). KPI direction: identity_reconciliation_exceptions_per_1000 = 17, DOWN (`data/reference/baseline_kpis.csv`). | In: surface conflicts; never fabricate a linkage when identifiers disagree (`AGENTS.md`). Out: autonomous COI correction. | Chain-of-identity corrections require propose → approve → execute → audit (`docs/06_security_privacy_assurance.md`). | Three OpenAPI identifier styles coexist (`patientId`, `patient_id`, `subjectIdentifier` in `contracts/api_v1.yaml`, `contracts/api_v2.yaml`, `contracts/api_v3.yaml`) and none is the global source of truth (`AGENTS.md`). | Reconcile CRM vs clinical vs `data/raw/patients.csv` for EVAL-002; reconstruct patient→collection→shipment→batch for P-00001 (`tests/test_repository.py`, `participant/DISCOVERY_CHECKLIST.md`). |
| Quality-release and infusion-readiness language is overloaded: journey_status includes `QA_HOLD` (59) and `INFUSION_READY` (57) (`data/raw/patients.csv`); MES `RELEASED` (378) vs QMS `RELEASED` (362) with 16 MES-vs-QMS conflicts (`data/raw/batches.csv`, `VERIFICATION.md`); legacy `product_ready()` treats `MFG_COMPLETE` or ERP `AVAILABLE` as ready (`src/cgt_orchestrator/legacy/status_rules.py`). | Preserve distinct states: QC complete ≠ QA released ≠ product ready ≠ infusion ready (`.cursor/rules/cgt-fde.mdc`). Measurable: qa_release_forecast_mae_hours 27.5 DOWN; cross_system_traceability_complete_pct 82.4 UP (`data/reference/baseline_kpis.csv`). | In: evidence-backed state reconstruction. Out: collapsing statuses in a single “ready” flag for operational decisions. | QA release requires QC evidence, disposition of blocking deviations and authorized electronic approval (`docs/sops/SOP-QA-014-v4.md`). Open deviations: 73 OPEN + 62 INVESTIGATING of 188 (`data/raw/deviations.csv`, `data/manifest.json`). | Seeded contradictions are challenge signals, not accidental dirt to wipe (`docs/07_v2_audit_and_changelog.md`). | Use `tests/test_legacy_expected_failures.py` as living defect register; do not convert xfail without a documented rule change (`AGENTS.md`). |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Mandate is operational truth and governed decision support, not a chatbot | `docs/01_problem_context.md` (Why this is an AI FDE problem); `README.md` (participant task is not “add an LLM”) | Case pack | High for synthetic estate; not a real GxP system (`README.md`) |
| Leadership outcome: fewer patient-at-risk cases, less manual coordination, fewer avoidable delays | `participant/CHALLENGE_BRIEF.md` opening paragraph | Case pack | Directional mandate; no numeric target in the brief itself |
| Synthetic baseline KPIs exist and are labelled synthetic | `data/reference/baseline_kpis.csv` rows median_vein_to_vein_days=21.8 through cross_system_traceability_complete_pct=82.4 | `data/manifest.json` seed 42001 | High for this fixture; not production telemetry |
| Dataset scale: 800 patients, 800 collections, 1600 shipments, 800 batches, 188 deviations | `data/manifest.json` counts; `python -m cgt_orchestrator.cli diagnostics` patient_count=800 | `data/manifest.json` | High; diagnostics independently confirms 800 |
| Seeded anomalies already quantified | `VERIFICATION.md` Diagnostic evidence: duplicate_mrn_count=2, impossible_shipment_time_count=9, mes_qms_conflict_count=16, slot_state_conflict_count=9, withdrawn_consent_count=5, expired_or_due_site_controls=6 | Diagnostics CLI | High for current SQLite snapshot `data/cgt_legacy.db` |
| QA, not manufacturing completion, owns product release | `docs/sops/SOP-QA-014-v4.md` Status: Effective | Policy | High as internal synthetic policy; not an external regulation |
| AI/agent recommendations must expose evidence, uncertainty, authority and audit metadata | `AGENTS.md` Non-negotiables | Case pack | Binding for this engagement |
| Architecture diagram is a governance description, not proven production behavior | `docs/03_architecture_current_state.md` warning paragraph | Current-state doc | Explicit uncertainty; must be validated against code, events and shadow files |
| Named operational actors appear in shadow evidence (planner2, ops_mgr, vendor, ops) | `shadow_ops/PatientPriority_MASTER.csv`; `shadow_ops/CourierEscalations.csv` owner column | Process evidence | Fictional names; roles are evidenced, employment relationship is not |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No named executive sponsor exists in the synthetic estate; “senior leadership” is unnamed | `participant/CHALLENGE_BRIEF.md` states senior leadership without a person | Engagement lead (assumption) | RACI and escalation remain role-based until a fictional named owner is assigned in Stage 01 sponsor artifact | `01_mandate_and_field_immersion/sponsor-owner.md` (to complete) |
| SOP-SCHED-003 v2 is Draft, not Effective | `docs/sops/SOP-SCHED-003-v2.md` Status: Draft | Scheduling / Quality (assumption) | Provisional slot reservations may not be a ratified enterprise rule | Effective SOP or explicit “draft treated as operating practice” decision |
| `data/manifest.json` still labels repo_name `..._v1` and version `1.0.0` while `repo_version` is `2.0.0` | File as written; `pyproject.toml` and API version are 2.0.0 | Packaging/steward | Version claims must be cited with the specific field used | `docs/07_v2_audit_and_changelog.md` (normalized project/API metadata to 2.0.0) |
| Architecture current-state C4 is intentionally incomplete | `docs/03_architecture_current_state.md` title and warning | Architecture discovery | Stage 02 must not treat the mermaid as ground truth | Code, `contracts/`, `data/raw/events.jsonl`, `shadow_ops/` |
| KPI targets are direction-only (UP/DOWN), not numeric SLOs | `data/reference/baseline_kpis.csv` target_direction column | Product / operations | Stage 03/07 must not invent percentage-point targets | Explicit SLO decision with owner |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Approved mandate and operating context

Do not advance to Stage 02 until the Stage 01 exit gate is defensible.
