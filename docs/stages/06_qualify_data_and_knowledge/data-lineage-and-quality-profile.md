# Data Lineage and Quality Profile

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 06 — Qualify Data & Knowledge  
**Participant status:** `COMPLETED`

## Stage question
Is the evidence trustworthy, permissible, traceable, representative and ready?

## Why this artifact exists
Part of **Data and knowledge readiness**.

## Upstream dependency
`05_model_the_domain/ubiquitous-language-glossary.md`.

## Evidence to inspect
- `data/manifest.json`; `diagnostics.py`; `docs/05_data_map.md`

## Case challenge
Lineage and defects—not file presence.

## Minimum content
Inventory, CRM→infusion lineage, quality.

## Relevant non-negotiable constraints
- Shadow notes do not override COI (`events.jsonl` dual time).

## Working scaffold
| Asset/source | Type | Owner | Authoritative for | Not authoritative for | Freshness | Permissible use | Known issue |
|---|---|---|---|---|---|---|---|
| `data/raw/crm_patient_export.csv` | CRM | CRM | crm_id, CRM DOB | Canonical person | Seed 42001 | Synthetic read | P-00079 `1959-12-23` |
| `data/raw/patients.csv` | Orch | Ops | `patient_key` | Global SoT | Seed 42001 | Synthetic | `MRN-389336` dup |
| `data/cgt_legacy.db` / `shadow_ops/` | Projection / workaround | Eng / planner | Joins / process notes | Identity SoT; MES/QMS | Derived/stale | Local; untrusted EVAL-006 | Dropped CRM DOB; EMAIL OVERRIDE |

| Data/fact | Origin | Transformations | Stores | Consumers | Version/time | Gap |
|---|---|---|---|---|---|---|
| Patient | CRM→clinical→orch | No merge (`patient_resolver.py`) | CSV+SQLite | `/identity/resolve` | Dual clocks | SQLite≠CSV |
| Collection→Shipment→Batch→QC→infusion | raw CSVs + `journey_status` | Statuses not collapsed; OPEN blocks | SQLite | `product_ready`; detector | departed/arrived | 9 bad times; 16 MES≠QMS |

| Asset | Completeness | Validity | Consistency | Uniqueness | Known issue | Fitness |
|---|---|---|---|---|---|---|
| 800 patients/batches; 1600 shipments | Full fixture | Homonyms; 9 impossible times | DOB/MRN; 16 MES/QMS | MRN n=2 | EVAL-002/003 | Fit to **detect**, not merge |

## Evidence and traceability
| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Counts | `data/manifest.json` seed 42001 | Stage 02 | High for fixture |

## Open issues / assumptions
| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| CSV vs SQLite identity | Projection | Steward | Keep CSV resolver | EVAL-002 |

## Completion check
- [x] Complete; cited; conflicts kept; rights distinct.

## Handoff
**Stage exit contribution:** Data and knowledge readiness assessment
