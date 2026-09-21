# Semantic Model and Ontology

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 09 — Information, Knowledge & Retrieval Architecture  
**Participant status:** `COMPLETED`  
**Deliverable form:** Structured analysis / specification

## Stage question
How does enterprise evidence become canonical meaning, connected knowledge and runtime context?

## Why this artifact exists
Part of **Approved information architecture**. Not a KG-as-SoR (`docs/04_target_capabilities_not_prescribed_solutions.md`).

## Upstream dependency
`05_model_the_domain/ubiquitous-language-glossary.md`.

## Evidence to inspect
- `data/raw/patients.csv`; `data/raw/batches.csv`; `data/raw/shipments.csv`; `docs/05_data_map.md`

## Case challenge
Preserve Patient–Collection–Shipment–Batch and provenance; do not call JSON a graph.

## Minimum content
Semantic-layer columns plus ontology class table.

## Relevant non-negotiable constraints
- QC ≠ QA released ≠ product ready ≠ infusion ready. MES/QMS may diverge.

## Working scaffold
| Canonical fact/entity | Measure/dimension | Definition/grain | Time semantics | Source mapping | Owner |
|---|---|---|---|---|---|
| Patient | `patient_key` | Not MRN alone | dob attribute | CSV trio | COI |
| Shipment | `shipment_id` | OUTBOUND/RETURN | departed/arrived vs `events.jsonl` | `shipments.csv` | Logistics |
| Batch | `batch_id` | **Three** statuses | mfg dates | mes/erp/qms columns | QA owns QMS |

| Class/concept | Definition | Relationship | Constraint | Taxonomy | Provenance hook |
|---|---|---|---|---|---|
| Patient | Orch token | Collection, Consent | MRN dup ≠ merge | `journey_status` | `patient_resolver.py` |
| Shipment | Cryo move | Patient; return `batch_id` | Flag arrived before departed | direction | EVAL-003 |
| Batch | Autologous lot | Patient, Collection | `product_ready` needs QMS RELEASED | MES≠QMS RELEASED | SOP-QA-014-v4 |
| Consent / Deviation | Legal / quality | Patient; Batch | WITHDRAWN or OPEN blocks | ConsentState | EVAL-004; `deviations.csv` |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Dual batch statuses are the model | `data/raw/batches.csv` | Stage 05 | High |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| HOLD homonyms | Unproven same meaning | Domain | Keep source prefix | Glossary |

## Completion check
- [x] Minimum content complete. Claims cited. Conflicts preserved. Decision rights distinct. No upstream contradiction. N/A unused.

## Handoff
**Stage exit contribution:** Approved information architecture
