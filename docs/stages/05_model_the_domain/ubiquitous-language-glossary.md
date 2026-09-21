# Ubiquitous-Language Glossary

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 05 — Model the Domain  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured table / register

## Stage question
What does the business actually mean, decide and own?

## Why this artifact exists
This artifact is part of the evidence needed to reach **Domain and decision model**. It must be consistent with approved upstream artifacts; do not silently redefine earlier facts, semantics, thresholds or decision rights.

## Upstream dependency
Use the completed Stage 04 artifacts and explicitly referenced earlier artifacts. Never copy them into this file simply to satisfy a checklist.

## Evidence to inspect
- `data/raw/patients.csv`
- `data/raw/collections.csv`
- `data/reference/baseline_kpis.csv`
- `docs/05_data_map.md`
- `data/raw/crm_patient_export.csv`
- `docs/04_target_capabilities_not_prescribed_solutions.md`
- `docs/02_imperfection_layers.md`
- `data/raw/consents.csv`
- `docs/sops/SOP-LOG-007-v6.md`
- `docs/sops/SOP-LOG-007-v7.md`
- `docs/sops/SOP-QA-014-v4.md`
- `shadow_ops/emails/`
- `docs/sops/SOP-SCHED-003-v2.md`

## Case challenge
Resolve business meaning around Patient, Collection, Material, Shipment, Batch, QC Result, Deviation, Cryogenic Telemetry Observation. Preserve source-specific meanings where they are genuinely different rather than forcing false canonicalization.

## Minimum content
- Term
- Canonical definition
- Source meanings
- Synonyms
- Forbidden conflation
- Owner

## Relevant non-negotiable constraints
- AI cannot issue or execute clinical, quality-release, chain-of-identity or chain-of-custody decisions or replace QA Release Authority.
- Treatment-center, logistics, manufacturing and QMS state may diverge during outages or delayed events and must reconcile safely with temporal provenance.

## Working scaffold
| Term | Canonical definition | Source meanings | Synonyms | Forbidden conflation | Owner |
|---|---|---|---|---|---|
| Patient | Synthetic journey subject keyed by `patient_key` (e.g. P-00001) in orchestration data (`data/raw/patients.csv`). Not a real person (`README.md`). | CRM: `crm_patient_id` (CRM100001) + `patient_key` (`data/raw/crm_patient_export.csv`). Clinical: `clinical_subject_id` (SUBJ-CH-0001), column `status` instead of `journey_status`, `patient_alias` instead of `synthetic_name` (`data/raw/clinical_patient_export.csv`). API v1 `patientId`, v2 `patient_id`, v3 `subjectIdentifier` (`contracts/api_v1.yaml`, `api_v2.yaml`, `api_v3.yaml`). | Subject, CRM patient, clinical subject | Do not treat `patientId` / `patient_id` / `subjectIdentifier` / `mrn` as interchangeable without a documented crosswalk. Duplicate MRNs exist (count=2; `VERIFICATION.md`). | Clinical operations + MDM (assumption); evidence steward is orchestration `patient_key` |
| MRN | Source medical-record token on patient rows (`data/raw/patients.csv` `mrn`). | Same column in CRM and clinical exports; collisions exist (`MRN-389336`, `MRN-945144` each on two patients — diagnostics `duplicate_mrn_count=2`). | Medical record number | Do not use MRN as the unique join key. | Treatment center / clinical export |
| Chain of Identity (COI) | Material identity token `coi_id` linking collection, shipment and batch (e.g. COL-00001 / SHP-O-00001 / BAT-00001 share `COI-9655125`) (`data/raw/collections.csv`, `data/raw/shipments.csv`, `data/raw/batches.csv`). | Checklist requires competing identity resolution (`participant/DISCOVERY_CHECKLIST.md`). EVAL-002: surface DOB/source conflict, do not silently merge (`evals/cases.csv` P-00079). | COI, identity | Do not equate COI with `patient_key` or `bag_id`. Do not auto-correct COI (`docs/06_security_privacy_assurance.md`). | Quality / COI process owner (assumption) |
| Collection | Apheresis/source-material event `collection_id` with `bag_id`, `volume_ml`, `cell_count_10e9`, `viability_pct`, `quality_flag` (`data/raw/collections.csv`). | quality_flag observed: ACCEPTABLE 638, LOW_VIABILITY 162. Event type `COLLECTION_COMPLETED` source CLINICAL (`data/raw/events.jsonl` EVT-00001-01). | Apheresis, source material | Do not treat collection complete as manufacturing-ready or slot-confirmed. | Treatment center |
| Shipment / Chain of Custody | Cryogenic movement `shipment_id` with `direction` OUTBOUND (800) or RETURN (800), `status` BOOKED 200 / IN_TRANSIT 198 / DELIVERED 1202, `temp_excursion` TRUE 19 (`data/raw/shipments.csv`). | Event types `SHIPMENT_DISPATCHED`, `SHIPMENT_RECEIVED` source LOGISTICS (`data/raw/events.jsonl`). Courier escalations FLIGHT/HANDOFF/TEMP_SENSOR/CUSTOMS (`shadow_ops/CourierEscalations.csv`). | Logistics movement, custody | Do not assume DELIVERED implies in-spec temperature or intact COI. Impossible timelines exist (SHP-O-00083 arrived before departed). | Logistics |
| Cryogenic Telemetry Observation | Sensor sample: `temperature_c`, `quality`, `gps_zone`, `timestamp` (`data/raw/cryogenic_telemetry.csv`; 12800 points, `data/manifest.json`). | SOP-LOG-007 v6 (Superseded): any point above -120 C = automatic failure. SOP-LOG-007 v7 (Effective 2026-05-01): single point is not disposition; evaluate duration, sensor quality, cumulative profile, shipper integrity; human-authorized. Legacy code: `temp_c > -120.0` (`src/cgt_orchestrator/legacy/status_rules.py:19-23`). | Excursion, sensor point | Do not treat one telemetry point, a courier note, or `temp_excursion=TRUE` as QA disposition. | Quality + Logistics |
| Manufacturing slot | Capacity reservation `slot_id` with dual state: `scheduler_state` CONFIRMED 406 / HOLD 206 / RESERVED 188 and `mes_state` PLANNED 517 / READY 270 / CANCELLED 13 (`data/raw/manufacturing_slots.csv`). | Shadow copy adds `planner_note` (`shadow_ops/ManufacturingSlots_FINAL_v7.csv`). SOP-SCHED-003 v2 Draft: may provisionally reserve before reimbursement; must revalidate before clinical milestones. Legacy `SlotService` status `RESERVED` with new UUID each call (`slot_service.py:10`). | Reservation, schedule hold | Scheduler HOLD ≠ QMS HOLD ≠ journey QA_HOLD. mes_state READY ≠ product RELEASED ≠ INFUSION_READY. CONFIRMED can coexist with MES CANCELLED (n=9). | Scheduling / MES |
| READY | **Not a single enterprise state.** Observed as `mes_state=READY` on 270 slots (`data/raw/manufacturing_slots.csv`) and as substring of `INFUSION_READY` on 57 patients (`data/raw/patients.csv`). Legacy boolean `ready` from `patient_ready()` (`src/cgt_orchestrator/api.py:33`). | Checklist explicitly asks to identify competing READY/HOLD/COMPLETE/RELEASED (`participant/DISCOVERY_CHECKLIST.md`). | mes_state READY; API `ready` | Forbidden: collapsing MES READY, product ready, QA released, and infusion ready. | Split: MES (slot READY); Clinical (INFUSION_READY); do not assign a single owner |
| HOLD | **Homonym across sources.** `scheduler_state=HOLD` (206 slots); `qms_release_status=HOLD` (145 batches); `journey_status=QA_HOLD` (59 patients) (`data/raw/manufacturing_slots.csv`, `data/raw/batches.csv`, `data/raw/patients.csv`). | Shadow slots also use scheduler HOLD (`shadow_ops/ManufacturingSlots_FINAL_v7.csv`). | QA_HOLD, QMS HOLD, scheduler HOLD | Do not assume one HOLD blocks all downstream systems. Legacy `patient_ready` only excludes `ENROLLED`, so QA_HOLD can still be “ready” (`status_rules.py:16`). | Scheduling vs QA — must remain distinct |
| RELEASED | **Competing release languages.** `mes_status=RELEASED` 378 batches vs `qms_release_status=RELEASED` 362; 16 MES RELEASED with QMS not RELEASED (`data/raw/batches.csv`, `VERIFICATION.md`). SOP-QA-014 v4: manufacturing completion is not product release. | Legacy `product_ready` treats MES `MFG_COMPLETE` or `RELEASED` **or** ERP `AVAILABLE` as ready (`status_rules.py:7-9`). ERP `AVAILABLE` 520 vs QMS RELEASED 362. | MES released, QA released, ERP available | Forbidden: MES RELEASED = QA RELEASED = ERP AVAILABLE = INFUSION_READY. | QA Release Authority for product release (`docs/sops/SOP-QA-014-v4.md`) |
| MFG_COMPLETE | MES manufacturing-complete status (142 batches) (`data/raw/batches.csv`). | xfail: `product_ready` must be false when MES=MFG_COMPLETE, ERP=AVAILABLE, QMS=PENDING (`tests/test_legacy_expected_failures.py:6-8`). | Manufacturing complete | Not QA release; not infusion ready. | MES / manufacturing |
| Batch | Patient-specific manufacturing lot `batch_id` with `coi_id`, `site_id`, `mes_status`, `erp_status`, `qms_release_status` (`data/raw/batches.csv`). mes_status also includes QC_TESTING 135, QA_HOLD 127, INVESTIGATION 18. | Event `MANUFACTURING_STARTED` source MES (`data/raw/events.jsonl` EVT-00001-04). | Lot, product (loosely) | Batch existence ≠ released product. Open QMS investigation is not “in process” in ERP terms. | Manufacturing + QA |
| QC Result | Assay record `qc_id` with assay IDENTITY/POTENCY/STERILITY/VIABILITY/PURITY/SAFETY (800 each) and result PASS 3764 / OOT 594 / OOS 226 / PENDING 216 (`data/raw/qc_results.csv`). Distinct `sampled_at` vs `reported_at`. | SOP-QA-014: QA release requires required QC evidence. INJ-004 sterility assay backlog (`scenarios/inject_catalog.csv`). | Assay, OOT, OOS | QC PASS ≠ QA RELEASED. PENDING/OOT/OOS must remain visible (`docs/05_data_map.md`). | QC / LIMS |
| Deviation | Quality exception `deviation_id` type ASSAY_INVESTIGATION 45, LABEL_RECONCILIATION 40, EQUIPMENT_ALARM 39, PROCESS_DEVIATION 33, TEMPERATURE_EXCURSION 31; severity CRITICAL 50 / MAJOR 95 / MINOR 43; status OPEN 73 / INVESTIGATING 62 / CLOSED 53 (`data/raw/deviations.csv`). Repository treats non-CLOSED as open (`repository.py:31-32`). | Linked via `linked_event_id` (e.g. DEV-00001 → EVT-00001-MFG). | Investigation, exception | OPEN/INVESTIGATING is a hard feasibility constraint for QA release (charter / SOP-QA-014). Do not auto-close. | QMS / QA |
| Consent | `consent_id` status VALID 751 / EXPIRED_VERSION 44 / WITHDRAWN 5; versions v3 712 / v2 88 (`data/raw/consents.csv`). | EVAL-004 P-00157 CNS-00157 WITHDRAWN; no autonomous continuation (`evals/cases.csv`). Legacy `patient_ready` ignores consent (`status_rules.py:15-16`). | Consent lifecycle | WITHDRAWN ≠ expired version. Valid consent is not authorization. | Clinical / privacy |
| Authorization | Payer/reimbursement `auth_id` status APPROVED 468 / PENDING 166 / CONDITIONAL 161 / DENIED 5 (`data/raw/insurance_authorizations.csv`). | P-00157 remains APPROVED after consent withdrawal (AUTH-00157). INJ-010 authorization withdrawn (`scenarios/inject_catalog.csv`). SOP-SCHED-003 v2 Draft allows provisional slot before reimbursement. | Financial authorization, payer status | Authorization ≠ eligibility ≠ consent ≠ site qualification. | Market access / commercial |
| Infusion ready | `journey_status=INFUSION_READY` (57 patients) (`data/raw/patients.csv`). Conceptual last pre-infusion stage before INFUSED (`docs/01_problem_context.md`). | Clinical export uses column `status` with the same token (`data/raw/clinical_patient_export.csv`). | Product ready (incorrect synonym in legacy heuristic) | Infusion ready is not QA released and not MES READY. Conditioning/infusion remain clinical. | Treatment center / clinical |
| Event time vs recorded time | `occurred_at` is event time; `recorded_at` is ingestion/recorded time (`data/raw/events.jsonl`; `AGENTS.md`). | EVT-00001-00: occurred 2026-01-06T20:00:00Z, recorded 20:17:00Z; EVT-00001-01 recorded 1h55m later than occurred. | As-of, ingest time | Latest `recorded_at` is not latest real-world event (`.cursor/rules/cgt-fde.mdc` item 2). | Data / integration |
| Product ready (legacy) | Defective boolean: MES MFG_COMPLETE/RELEASED or ERP AVAILABLE (`src/cgt_orchestrator/legacy/status_rules.py:7-9`). | Exposed at GET `/legacy/readiness/{patient_key}` with warning “legacy heuristic; not a validated clinical/quality decision” (`src/cgt_orchestrator/api.py:33`). | ready (API field) | Must not be used as QA Release Authority. | None — marked unsafe; QA owns the real decision |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Observed journey_status inventory (10 values, counts above) | Distinct values in `data/raw/patients.csv` (800 rows; `data/manifest.json`) | Stage 02 brownfield L5 | High for this seed; vocabulary is fixture-specific |
| READY/HOLD/RELEASED are homonyms across scheduler, MES, QMS, journey | `data/raw/manufacturing_slots.csv`; `data/raw/batches.csv`; `data/raw/patients.csv`; `participant/DISCOVERY_CHECKLIST.md` | Stage 02 open issue on HOLD semantics | High that strings collide; low that business process intends one meaning |
| QA release is distinct from manufacturing complete | `docs/sops/SOP-QA-014-v4.md`; xfail `test_product_not_ready_until_qa_released` | Stage 01 charter | High as synthetic policy + failing legacy test |
| Effective excursion rule is v7, not v6 | `docs/sops/SOP-LOG-007-v7.md` vs v6 vs `status_rules.py:19-23` | Stage 02 L11 | High |
| P-00079 identity conflict is DOB, not MRN | CRM `1959-12-23` vs patients/clinical `1959-12-22` (`data/raw/crm_patient_export.csv`, `data/raw/clinical_patient_export.csv`, `data/raw/patients.csv`); `evals/cases.csv` EVAL-002 | Stage 02 L3 | High for this patient_key |
| Canonical capabilities forbid destroying source evidence | `docs/04_target_capabilities_not_prescribed_solutions.md` | Stage 01 | Binding design constraint |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| No data dictionary maps scheduler HOLD to QMS HOLD | Homonymous values only | Domain workshop (assumption) | Retrieval/graph models must keep source-qualified statuses | Stage 09 source-to-canonical mapping |
| SOP-SCHED-003 remains Draft | `docs/sops/SOP-SCHED-003-v2.md` | Scheduling / QA | Provisional slots before authorization may be informal practice | Effective SOP |
| “Material” is not a table; closest records are collection + bag_id + coi_id | `data/raw/collections.csv`; `docs/05_data_map.md` | Domain | Do not invent a Material master | Explicit bounded-context decision |
| Clinical `status` vs orchestration `journey_status` equality is unverified at scale | Headers differ; sampled P-00001/P-00002 match | Data quality | Identity resolution must compare both fields | Cross-file reconciliation job with evidence |
| Owner column is organizational, not named in-repo | SOPs name processes, not people | Stage 01 sponsor assumption | RACI remains role-based | Sponsor-owner artifact |

## Completion check
- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic and AI decision rights are distinguishable where relevant.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] `NOT APPLICABLE`, if used, includes rationale, accountable approver and downstream consequence.

## Handoff
**Stage exit contribution:** Domain and decision model

Do not advance to Stage 06 until the Stage 05 exit gate is defensible.
