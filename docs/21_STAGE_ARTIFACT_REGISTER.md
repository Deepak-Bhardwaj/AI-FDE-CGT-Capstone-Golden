# One-to-One 21-Stage Artifact Register

**Canonical machine-readable register:** `21_STAGE_ARTIFACT_REGISTER.csv`
**Framework source:** `FDE_PDF.pdf`, Operating Model pages headed Surya 2-12
**Challenge deliverables source:** `source_baseline/participant/CHALLENGE_BRIEF.md`
**Scope of assessment:** Synthetic academic capstone; not live deployment or independent assurance

Each CSV row maps **one named essential artifact** from the 21-stage operating model, or one merged-repository extra, to its primary canonical file. `S13-X01` is an extra training-sequence PRD row; `Snn-N*` rows are named-folder participant artifacts under `docs/stages/`; `Snn-M01`–`Snn-M04` are the merged AI intelligence, identity reconciliation, Control Tower webapp and governance/audit capabilities. Related evidence may exist elsewhere, but the CSV names one place to start answering a question. A path of `-` means that there is no canonical file, not that an artifact was lost in a different folder.

## Dual stage-folder trees

`docs/stages/` holds two complementary trees. Neither tree is stage approval or external validation.

| Tree | Role |
|---|---|
| `docs/stages/stage_NN/` | Original golden-repo PDF essentials, reviews, gate records and machine-readable evidence |
| `docs/stages/NN_named_workflow/` | Merged participant artifacts (charter, C4, delivery specification, defect report, runbooks, AIMS, 90-day roadmap) |

PDF essential rows keep pointing at `stage_NN/` so an `EXTERNAL_REQUIRED` or `CONDITIONAL_NOT_SELECTED` PDF artifact is not relabelled complete merely because a named-folder narrative exists.

## Status vocabulary

| Status | Meaning | Permitted claim |
|---|---|---|
| `PRESENT_INTERNAL` | A suitable synthetic specification/implementation/evidence file exists | Prepared or internally verified in this academic scope only |
| `PARTIAL` | File exists but PDF scope, approval, execution or evidence is incomplete | Point to both current evidence and the stated exit gap |
| `MISSING` | No canonical deliverable exists | Create a scoped artifact or retain the gap |
| `CONDITIONAL_NOT_SELECTED` | The architecture explicitly rejected or has no such feature/supplier | Do not fabricate model/RAG/multi-agent or retirement records |
| `EXTERNAL_REQUIRED` | Real people, systems, contracts or observed outcomes are necessary | Keep open until accountable external evidence is supplied |
| `COMPLETED` | Merged named-folder or webapp deliverable is present and internally finished | Academic completion only; not live service, owner sign-off or observed benefit |
| `VERIFIED` | Merged intelligence, reconciliation or governance code is implemented and internally tested | Academic verification only; observe/recommend, never-merge-on-conflict, hash-chained audit; not production assurance |

`COMPLETED` and `VERIFIED` apply to **merged extras** (`-N`, `-M`). They do not upgrade PDF rows. A stage can have `VERIFIED` intelligence and still have `EXTERNAL_REQUIRED` live-deployment or observed-benefit artifacts.

The register currently has **293 rows**, covering **21 stages**:

- **185** PDF essential rows plus the training PRD: **88** `PRESENT_INTERNAL`, **72** `PARTIAL`, **16** `CONDITIONAL_NOT_SELECTED`, **9** `EXTERNAL_REQUIRED`, **0** missing
- **24** named-folder merged artifacts (`-N`): all `COMPLETED`
- **84** merged-capability rows (**4 per stage**): **63** `VERIFIED` (intelligence, reconciliation, governance) and **21** `COMPLETED` (Control Tower webapp)

Status counts and exact path validity are tested by `tests/test_artifact_register.py`. Counts are not a completion score: one present file may still lack sign-off, and one conditional artifact may correctly remain absent.

## Merged capabilities on every stage

Every stage **01–21** has four explicit extra rows. Canonical code/docs are real files in this repository. Status values are academic `COMPLETED` or `VERIFIED` as required for the merged extras; they are **not** production, clinical, regulatory or independently assured claims.

| Stage | AI intelligence `M01` | Identity reconciliation `M02` | Control Tower webapp `M03` | Governance and audit `M04` |
|---:|---|---|---|---|
| 01 | `VERIFIED` — `exception_detector.py`; charter forbids replacing QA Release Authority | `VERIFIED` — `patient_resolver.py`; never merge on conflict | `COMPLETED` — packaged `web/index.html`; UI is not the Stage 01 mandate artifact | `VERIFIED` — Stage 01 RACI; sponsor signoff still external |
| 02 | `VERIFIED` — exceptions from frozen CSVs | `VERIFIED` — source identifiers stay visible | `COMPLETED` — reconstructed journeys in the browser | `VERIFIED` — shadow-ops evidence governed; field interviews absent |
| 03 | `VERIFIED` — ranks process failures; no observed-benefit claim | `VERIFIED` — collisions explained, not collapsed | `COMPLETED` — SCQA framed in the demo UI | `VERIFIED` — POC thresholds distinct from outcomes |
| 04 | `VERIFIED` — advisory; AI-off path retained | `VERIFIED` — human-authorized identity; no COI merge | `COMPLETED` — UI cannot issue prohibited actions | `VERIFIED` — prohibited-use policy is G1 containment |
| 05 | `VERIFIED` — glossary-aligned exception language | `VERIFIED` — source-specific patient keys | `COMPLETED` — screens use ubiquitous language | `VERIFIED` — QA Release Authority stays human |
| 06 | `VERIFIED` — lineage-located CSV fields; unknown stays unknown | `VERIFIED` — `source_baseline` CSVs are the record | `COMPLETED` — UI is not a data-edit surface | `VERIFIED` — access register academic only |
| 07 | `VERIFIED` — EVAL properties; detector does not treat | `VERIFIED` — EVAL-002 recommends, does not merge | `COMPLETED` — reviewer/exception demonstration surfaces | `VERIFIED` — oversight protocol; human studies not run |
| 08 | `VERIFIED` — deterministic intelligence; RAG not selected | `VERIFIED` — no model merge | `COMPLETED` — vanilla Control Tower selected; `web_frontend` is prototype | `VERIFIED` — academic G2 only |
| 09 | `VERIFIED` — typed assertions; no graph/vector store | `VERIFIED` — non-fungible source identifiers | `COMPLETED` — UI consumes evidence contracts | `VERIFIED` — provenance envelope is the audit contract |
| 10 | `VERIFIED` — `digital_twin.py` in target C4; RAG rejected | `VERIFIED` — `/reconcile/patient` behind bearer read | `COMPLETED` — as-built academic container UI | `VERIFIED` — authorize + audit append in C4 |
| 11 | `VERIFIED` — `services/intelligence.py` ranking only | `VERIFIED` — assistant cannot execute merge | `COMPLETED` — copilot off by default and recommendation-only | `VERIFIED` — handoff outside the authority path |
| 12 | `VERIFIED` — intelligence outside QA release | `VERIFIED` — merge-on-conflict denied | `COMPLETED` — governance pages demo-scoped | `VERIFIED` — named-folder threat model + hash chain |
| 13 | `VERIFIED` — observe/recommend in delivery spec | `VERIFIED` — FR-02 specified for academic build | `COMPLETED` — packaged `web/` in the spec | `VERIFIED` — ADRs name controls; owner approval pending |
| 14 | `VERIFIED` — `/intelligence/exceptions` + `AuditService` | `VERIFIED` — `patient_resolver.py` on `source_cases` | `COMPLETED` — governance section in vanilla `web/` | `VERIFIED` — SHA-256 `audit_service.py` on `storage.py` |
| 15 | `VERIFIED` — internal TEVV/red-team; no independent assurer | `VERIFIED` — catalog covers identity conflict | `COMPLETED` — packaged page in the academic test surface | `VERIFIED` — governance APIs internally tested |
| 16 | `VERIFIED` — `predictive_logistics.py` advisory only | `VERIFIED` — identity conflict stays human work | `COMPLETED` — local Control Tower start in the runbook | `VERIFIED` — named-folder operational runbook |
| 17 | `VERIFIED` — delay predictions do not expand autonomy | `VERIFIED` — no live identifier auto-reconcile | `COMPLETED` — academic browser demo; no real-user adoption | `VERIFIED` — local simulation; real override logs external |
| 18 | `VERIFIED` — digital twin traces; not production drift | `VERIFIED` — unresolved identity is not silently healed | `COMPLETED` — local operations view | `VERIFIED` — local audit metrics only |
| 19 | `VERIFIED` — technical feasibility, not proven benefit | `VERIFIED` — explainable conflicts, not a production MPI | `COMPLETED` — executive demo persona | `VERIFIED` — restrict/change recommendation |
| 20 | `VERIFIED` — AI stays off for real data until CAPAs close | `VERIFIED` — open identity CAPAs; no real-data merge | `COMPLETED` — UI remains academic under restrict/change | `VERIFIED` — internal audit/CAPA containment |
| 21 | `VERIFIED` — reusable exception patterns; disposable runtime | `VERIFIED` — resolver pattern catalogued | `COMPLETED` — frontend patterns as reusable IP | `VERIFIED` — local POC databases disposed; no enterprise access to revoke |

Canonical merged-code starting points:

- Intelligence: `src/fde_capstone/intelligence/` (`exception_detector.py`, `digital_twin.py`, `predictive_logistics.py`, `exceptions_routes.py`) and `src/fde_capstone/services/intelligence.py`
- Reconciliation: `src/fde_capstone/reconciliation/patient_resolver.py`
- Webapp: packaged Control Tower `src/fde_capstone/web/index.html` (React `src/fde_capstone/web_frontend/` is a prototype drop, not the live tower)
- Governance: `src/fde_capstone/services/audit_service.py` (hash-chained SQLite audit) plus named-folder threat model, RACI and runbook

## Architecture interpretation

The PDF's stage **output/input** phrases are higher-level gates. Stages 1-14 can be prepared or internally built on this synthetic package. Stage 15's *independently assured release candidate*, Stage 16's *operationally and legally ready release*, Stage 17's *controlled live service*, Stage 18's *operational performance*, and Stage 19's *observed benefits* cannot be achieved merely by local simulations. The Stage 20 restrict/change decision is the correct containment while external CAPAs remain open. Stage 21 records disposal of local runtime instances, not retirement of a real enterprise system.

Merged `COMPLETED`/`VERIFIED` rows record that intelligence, reconciliation, webapp and governance **exist in this repository** and are internally exercised. They do not convert those PDF gates into live or independently assured exits.

## Client-challenge deliverables beyond the named PDF artifact rows

The v2 client challenge explicitly requires a **patient-level current-state reconstruction**, **migration strategy** and **90-day roadmap**. Their canonical locations are `docs/stages/stage_02/07_SUPPLIED_PATIENT_JOURNEY_SOURCE_RECONSTRUCTION.md`, `docs/stages/stage_13/08_BROWNFIELD_MIGRATION_STRATEGY.md` and `docs/stages/stage_20/06_PRODUCTION_GAP_AND_90_DAY_ROADMAP.md`. The reconstruction covers six supplied synthetic examples only; the roadmap is a proposed funding/evidence plan, not an automatic pilot approval. The merged named-folder copy of the 90-day view is `docs/stages/21_retire_and_capture_reusable_ip/90-day-roadmap.md`.

The training delivery sequence additionally expects a standalone **PRD** before code and app. Its canonical location is `docs/stages/stage_13/06_PRODUCT_REQUIREMENTS_DOCUMENT.md`; Capstone Owner review is still pending.

## Maintenance rule

For each changed artifact, update the CSV row's canonical path, status, accountable role and exit evidence. Never mark an item `PRESENT_INTERNAL`, `COMPLETED` or `VERIFIED` solely because a filename exists. Before changing a stage to approved/live/production/benefit-proven, attach named owner approval and independent or observed evidence in a gate record. Scope or authority changes re-open Stage 4/7/10/12/13/15 assessments.
