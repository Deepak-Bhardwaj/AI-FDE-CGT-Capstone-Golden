# Technical Defect Resolution Report

**Case:** Cell & Gene Therapy (CGT) Patient-to-Batch Orchestration  
**Stage:** 14 — Engineer (Spec-Driven Development)  
**Audience:** Trainer / executive engineering review  
**Scope:** Conversion of three `@pytest.mark.xfail` legacy defects, plus POC 1 identity reconciliation  
**Governing artifacts:** `AGENTS.md`, `13_approve_adrs_and_delivery_specification/delivery-specification.md` (FR-02, FR-04, FR-05, FR-07, FR-08), `docs/sops/SOP-QA-014-v4.md`, `docs/sops/SOP-LOG-007-v7.md`

## How to read this briefing

The brownfield estate was *runnable but semantically unsafe*. Three tests were marked `xfail` on purpose: they encoded known production-class defects, not flaky CI. Stage 14 converted those tests to passing assertions **without weakening them**, and added a fourth capability: explainable patient-identifier reconciliation.

This work is **deterministic engineering**, not an LLM feature. We did **not** globally “clean” seeded contradictions in `data/raw/` (`AGENTS.md`: many inconsistencies are intentional challenge signals). We changed the *decision logic* that was misinterpreting that evidence.

**Original xfail register** (`tests/test_legacy_expected_failures.py`, pre-fix):

| Test | Encoded defect | Spec ID |
|---|---|---|
| `test_product_not_ready_until_qa_released` | MES complete / ERP available treated as QA release | FR-04 |
| `test_single_excursion_point_not_automatic_failure` | Superseded SOP-LOG-007 v6 point threshold | FR-08 |
| `test_slot_retry_is_idempotent` | Every retry minted a new reservation UUID | FR-07 |

**Related increment (not originally xfail, same rule file):** `patient_ready()` ignored consent (`FR-05`, EVAL-004).  
**POC 1:** `src/cgt_orchestrator/reconciliation/patient_resolver.py` (`FR-02`, EVAL-002).

---

## Defect 1 — QA release conflated with manufacturing complete

**Test:** `test_product_not_ready_until_qa_released`  
**Code:** `src/cgt_orchestrator/legacy/status_rules.py` → `product_ready()`  
**Policy:** `docs/sops/SOP-QA-014-v4.md` (Effective)

### 1. The symptom (what was failing)

The test constructed a batch that manufacturing and ERP would consider “done”:

```python
{'mes_status': 'MFG_COMPLETE', 'erp_status': 'AVAILABLE', 'qms_release_status': 'PENDING'}
assert product_ready(b) is False
```

Legacy `product_ready()` returned **True**. Quality had not released the product (`qms_release_status=PENDING`), but the function still declared it ready.

The old implementation was a single boolean expression:

```python
return batch.get("mes_status") in {"MFG_COMPLETE", "RELEASED"} or batch.get("erp_status") == "AVAILABLE"
```

Any one of three *different* systems could flip the gate. MES `RELEASED` (manufacturing language) was treated as equivalent to QMS `RELEASED` (quality-release language). ERP `AVAILABLE` was treated as equivalent to authorized product release.

### 2. The root cause (the technical flaw)

Three bad patterns compounded:

1. **Homonymous strings, no state machine.** `RELEASED` appears in MES and QMS with different meaning (`data/raw/batches.csv`; 16 rows where MES is `RELEASED` and QMS is not). The code compared raw strings and collapsed those meanings.
2. **OR-logic across systems of record.** One optimistic signal (ERP available *or* MES complete) overrode the actual authority column (`qms_release_status`).
3. **Hard-coded heuristic instead of SOP.** SOP-QA-014 v4 states: manufacturing completion is not product release; QA release requires QC evidence, disposition of blocking deviations, and authorized electronic approval. None of those gates existed in code.

This is the classic brownfield pattern: a convenience boolean named `ready` that silently becomes a clinical/quality decision.

### 3. The business risk (the “so what?”)

In autologous CGT, the batch *is* the patient. If manufacturing-complete is treated as released:

- A batch still on QA HOLD or PENDING can be labelled “product ready” and pushed into return logistics or infusion scheduling.
- Open deviations (73 OPEN + 62 INVESTIGATING in `data/raw/deviations.csv`) would not block the boolean.
- The patient could receive material that has not been quality-released — a chain-of-identity / patient-safety event, not a software inconvenience.
- Audit would show the system asserted readiness while QMS still said PENDING — an indefensible GxP story.

Trainer line: *“We were one OR-clause away from shipping a batch QA had not released.”*

### 4. The deterministic fix (how we solved it)

No model. An explicit **QMS release state machine** (`QmsReleaseState`: PENDING / HOLD / RELEASED) and conjunctive gates:

- Hard gate: `qms_release_status` must parse to `QmsReleaseState.RELEASED`.
- If deviation evidence is supplied: `OPEN` or `INVESTIGATING` blocks readiness.
- If QC evidence is supplied: required assays (IDENTITY, POTENCY, STERILITY, VIABILITY, PURITY, SAFETY) must be `PASS`.

MES and ERP statuses are still *visible* on the batch record. They are no longer *authoritative* for `product_ready()`. The original assertion is unchanged: MFG_COMPLETE + AVAILABLE + QMS PENDING → `False`.

`/legacy/readiness/{patient_key}` still returns a warning that this is not a validated clinical/quality decision. The boolean is a **deterministic gate**, not QA Release Authority.

### 5. The FDE non-negotiable enforced

- **Prefer explicit state machines over strings scattered in code** (`AGENTS.md` Engineering expectations).
- **Do not make consequential clinical, quality-release, chain-of-identity or chain-of-custody decisions autonomous** (`AGENTS.md` Non-negotiables).
- **Do not collapse QC complete, QA released, product ready, and infusion ready into one status** (`.cursor/rules/cgt-fde.mdc` item 3).
- **Add tests before fixing an intentional defect** — the xfail existed first; we converted it without weakening the assertion (`AGENTS.md`).

---

## Defect 2 — Cryogenic excursion auto-failed from a single sensor point

**Test:** `test_single_excursion_point_not_automatic_failure`  
**Code:** `src/cgt_orchestrator/legacy/status_rules.py` → `excursion_failed()`  
**Policy:** `docs/sops/SOP-LOG-007-v6.md` (Superseded) vs `docs/sops/SOP-LOG-007-v7.md` (Effective 2026-05-01)

### 1. The symptom (what was failing)

```python
assert excursion_failed(-118.0) is False
```

Legacy code implemented the **superseded** SOP:

```python
if temp_c is None:
    return False
return temp_c > -120.0
```

A single reading of −118 °C (two degrees above the old point threshold) was an automatic shipment failure. Duration, sensor quality, cumulative profile, and Quality review were ignored.

### 2. The root cause (the technical flaw)

1. **Stale policy encoded as a magic number.** The function *was* SOP-LOG-007 v6. Effective policy is v7. There was no policy version in the rule, so operators could not see they were running superseded logic.
2. **Point threshold treated as a disposition.** Telemetry is an observation. Failure is a Quality decision. The code collapsed observation → disposition in one comparison.
3. **No typed units or context.** A bare `float` named `temp_c` carried no duration, quality flag, or as-of time — the opposite of “treat units as typed data” and “model event time separately.”
4. **Automation of a human-authorized act.** SOP v7: consequential disposition remains human-authorized. The function made the computer the dispositioner.

INJ-002 in `scenarios/inject_catalog.csv` is exactly this case: a 47-second excursion near threshold, affecting shipment / quality / release.

### 3. The business risk (the “so what?”)

Cryogenic logistics for autologous product is unforgiving — but **false-failing** a shipment is also harm:

- A noisy or brief sensor spike could scrap a patient-specific batch that Quality would have judged intact after reviewing duration and shipper integrity.
- Vein-to-vein time is already 21.8 days median (`data/reference/baseline_kpis.csv`). An automatic fail can force recast, delay infusion, and put the patient at clinical risk from *process*, not from product.
- Conversely, if operations later “override” a noisy auto-fail informally (email, spreadsheet), you get the shadow-ops problem: dispositions outside the system of record.

Trainer line: *“A two-degree blip is a Quality review, not a death sentence for the batch — and not a license for the code to decide.”*

### 4. The deterministic fix (how we solved it)

Split **observation** from **disposition** (SOP-LOG-007 v7):

| Function | Meaning | Automatic failure? |
|---|---|---|
| `excursion_failed(temp_c)` | Disposition | **Never** from a point alone. True only if Quality already recorded `quality_disposition="FAILED"`. |
| `excursion_requires_quality_review(temp_c)` | HITL flag | True when `temp_c > -120`, so the signal is not discarded. |

Duration and sensor-quality arguments are accepted as evidence context; they do **not** auto-fail the shipment. The original test still asserts `excursion_failed(-118.0) is False`. We added a strengthening test that review is flagged and that only an explicit human FAILED disposition returns True.

### 5. The FDE non-negotiable enforced

- **Do not make consequential clinical, quality-release, chain-of-identity or chain-of-custody decisions autonomous** — excursion disposition is chain-of-custody / quality.
- **Separate conventional deterministic engineering from AI-assisted/agentic components** — this is a policy rule, not an agent.
- **Treat units as typed data, not free text** — temperature remains numeric; disposition is an explicit authorized field, not inferred from a threshold.
- **Add or update tests and document any changed assumptions** (`.cursor/rules/cgt-fde.mdc` item 7) — the module docstring records the SOP version change.

---

## Defect 3 — Slot reservation retries created duplicate capacity holds

**Test:** `test_slot_retry_is_idempotent`  
**Code:** `src/cgt_orchestrator/legacy/slot_service.py` → `SlotService.reserve()`  
**Scenario:** `scenarios/inject_catalog.csv` INJ-006 (Integration retry duplication)

### 1. The symptom (what was failing)

```python
s = SlotService()
a = s.reserve('P-00001', 'MFG-US-NJ-01')
b = s.reserve('P-00001', 'MFG-US-NJ-01')
assert a['reservation_id'] == b['reservation_id']
```

Every call executed:

```python
reservation = {"reservation_id": str(uuid.uuid4()), "patient_key": ..., "site_id": ..., "status": "RESERVED"}
self.reservations.append(reservation)
```

A timeout-and-retry from the integration hub (the realistic CGT pattern) created a **second** reservation with a new UUID for the same patient and site. The test expected idempotency; the code had none.

### 2. The root cause (the technical flaw)

1. **Non-idempotent cross-system command.** HTTP/API retries are normal. The command had no idempotency key and treated every call as a new write.
2. **UUID as identity of the business event.** The business event is “P-00001 holds a slot at MFG-US-NJ-01.” The code made “a random identifier we just minted” the identity.
3. **No compensation path.** After a retry, the estate could not tell which reservation was the real hold versus the ghost — exactly the distributed-transaction gap in `participant/DISCOVERY_CHECKLIST.md`.

This is not a string-flag bug; it is a **command-semantics** bug. Scheduling is still not QA — but duplicate holds starve other patients of suite time.

### 3. The business risk (the “so what?”)

Manufacturing slots are the scarce resource in autologous CGT (baseline slot utilization 71.0%, `data/reference/baseline_kpis.csv`):

- Duplicate reservations double-book a suite or block another patient’s slot.
- Downstream QC, return logistics, and conditioning windows drift (INJ-001 cascade pattern).
- Operators reconcile in `shadow_ops/ManufacturingSlots_FINAL_v7.csv` (“EMAIL OVERRIDE — moved Thu”) — the defect *feeds* shadow operations.
- If both UUIDs later bind to different MES jobs, you get two manufacturing identities for one patient material — a chain-of-identity nightmare.

Trainer line: *“A retry is not a second patient. Without idempotency, the integration timeout steals capacity from someone on the waitlist.”*

### 4. The deterministic fix (how we solved it)

`SlotService` now keys reservations by `idempotency_key`, defaulting to `patient_key:site_id` when the caller omits a key (so the original retry test passes):

- Replay of the same key returns the **same** `reservation_id`.
- Different patients still receive different IDs.
- An explicit `idempotency_key` (API header equivalent) is a distinct command, so callers can hold more than one logical reservation when they mean to.

This is still a scheduling command. Callers must revalidate treatment-center and quality gates before clinical milestones (`docs/sops/SOP-SCHED-003-v2.md`, Draft). We did not auto-confirm MES state.

### 5. The FDE non-negotiable enforced

- **Use idempotency for cross-system commands** (`AGENTS.md` Engineering expectations).
- **Every cross-system write must consider idempotency, compensation and audit evidence** (`.cursor/rules/cgt-fde.mdc` item 5).
- **Prefer reversible changes and explicit migration paths over big-bang replacement** — in-memory map plus documented default key; no MES rewrite.

---

## Defect 4 (related) — Journey “ready” ignored consent withdrawal

**Test added in the same increment:** `test_withdrawn_consent_blocks_patient_ready`  
**Code:** `patient_ready()` in `status_rules.py`  
**Eval:** `evals/cases.csv` EVAL-004 (P-00157, consent WITHDRAWN)

This was not one of the original three xfail markers, but it lived in the same function that consumed the defective `product_ready()` and is required by FR-05.

### 1. The symptom

Legacy `patient_ready(patient, batch)` returned True whenever `journey_status` was not `ENROLLED` and `product_ready(batch)` was True. Consent, authorization, site qualification, and shipment certainty were ignored. P-00157 has consent `WITHDRAWN` (`data/raw/consents.csv` CNS-00157) while authorization is still `APPROVED` and journey is `IN_MANUFACTURING`.

### 2. The root cause

Hidden-dependency bug: the boolean looked at the patient row and the batch row only. The legally and ethically load-bearing records sit in other tables. String exclusion of a single journey status (`not ENROLLED`) was used as a proxy for “safe to continue.”

### 3. The business risk

Continuing manufacture, release, or infusion after consent withdrawal is an unauthorized processing of human material — a rights, privacy, and chain-of-identity failure, not a scheduling miss. EVAL-004 expected property: *no autonomous consequential continuation*.

### 4. The deterministic fix

`patient_ready()` now accepts consents (and optional authorizations, deviations, QC). `ConsentState` is an explicit enum. `WITHDRAWN` and `EXPIRED_VERSION` force `False`. `DENIED` authorization also blocks when those records are provided. `/legacy/readiness` now passes journey consents into the gate and still carries the non-clinical warning.

### 5. The FDE non-negotiable enforced

- **Do not make consequential clinical … decisions autonomous.**
- **Prefer explicit state machines over strings scattered in code** (`ConsentState` vs `!= "ENROLLED"`).

---

## POC 1 — Patient identifier reconciliation (`patient_resolver.py`)

**Capability:** FR-02 / EVAL-002  
**Code:** `src/cgt_orchestrator/reconciliation/patient_resolver.py`  
**Tests:** `tests/test_patient_reconciliation.py`  
**Surfaces:** `python -m cgt_orchestrator.cli reconcile --patient-key P-00079`; `GET /identity/resolve`

This was not an xfail. It is the first *new* product increment: explainable identity resolution across CRM, clinical, and orchestration — **without treating SQLite as the global source of truth**.

### 1. The symptom (what was failing in the estate)

The orchestration table, CRM export, and clinical export all carry identifiers for the same synthetic people, but they are not a single clean key:

| Source | Identifier | Evidence |
|---|---|---|
| Orchestration | `patient_key` (e.g. P-00079) | `data/raw/patients.csv` |
| CRM | `crm_patient_id` (e.g. CRM100079) | `data/raw/crm_patient_export.csv` |
| Clinical | `clinical_subject_id` (e.g. SUBJ-US-0079) | `data/raw/clinical_patient_export.csv` |
| Contracts | `patientId` / `patient_id` / `subjectIdentifier` | `contracts/api_v1.yaml`, `api_v2.yaml`, `api_v3.yaml` |

Concrete failures the resolver must catch:

- **EVAL-002 / P-00079:** same `patient_key`, CRM DOB `1959-12-23` vs clinical and orchestration `1959-12-22`. A naive merge would pick one DOB and hide the conflict.
- **Duplicate MRN `MRN-389336`:** P-00532 and P-00713. Joining on MRN would fuse two patients.
- **Cross-walk collision:** CRM100001 (P-00001) + clinical SUBJ-US-0079 (P-00079) must not become one person.
- SQLite `patients.dob` for P-00079 is `1959-12-22` — **the database already dropped the CRM disagreement.** If we had trusted one table, EVAL-002 would be invisible.

### 2. The root cause (the technical flaw)

1. **Single-store fallacy.** `data/cgt_legacy.db` looks like a source of truth; it is a projection. CRM vs clinical conflict lives only in the CSV exports.
2. **Identifier soup without a crosswalk policy.** Three OpenAPI shapes and four identifier types invite “just join on MRN.”
3. **Silent merge as the default engineering instinct.** Brownfield teams “fix” DOB mismatches by overwriting. That fabricates a canonical person.
4. **No uncertainty object.** Legacy readiness returned `{ready: bool}`. Identity needs evidence, confidence, and an authority flag — or humans cannot review it.

### 3. The business risk (the “so what?”)

Chain of identity is the CGT equivalent of “the right product for the right patient”:

- Merging two MRNs can attach patient A’s apheresis bag to patient B’s manufacturing slot.
- Picking CRM’s DOB without review can fail eligibility or site matching rules against the treatment-center record.
- Infusing the wrong autologous product is a catastrophic identity event; there is no “recall and replace from inventory” in the usual sense — the product was made from *that* patient’s cells.

Trainer line: *“We would rather show a 0.55 confidence and a DOB conflict than invent a patient.”*

### 4. The deterministic fix (how we solved it)

`PatientResolver` is a **read-only, local CSV correlator**. No LLM. No write-back to QMS/CRM.

Algorithm:

1. Resolve each supplied identifier (orchestration id, CRM id, clinical id, MRN) to a *set* of `patient_key` values.
2. If those sets imply **more than one** `patient_key` → `resolved_patient_key=""`, confidence `0.0`, `requires_human_review=True`. No fused record.
3. If they agree on one key → compare `dob`, `mrn`, `center_id` **across all three files**. Attribute disagreement lowers confidence (e.g. P-00079 → `0.55`) and sets HITL. Both DOB values remain in `evidence`. There is no `canonical_dob` field.
4. Response contract: `{resolved_patient_key, confidence_score, evidence, requires_human_review}` plus `conflicts`, `authority_requirement` (`human-chain-of-identity` when HITL), and `rule_version`.

This observes and correlates. It does **not** execute a COI correction. That remains propose → approve → execute → audit (`docs/06_security_privacy_assurance.md`).

### 5. The FDE non-negotiable enforced

- **Never fabricate a patient/material/batch linkage when identifiers conflict. Represent uncertainty and evidence.**
- **Do not treat any single database/table/API as the global source of truth without evidence** — resolver reads three CSVs, not only SQLite.
- **Keep patient/material/batch identity resolution explainable.**
- **Do not “repair” synthetic inconsistencies globally** — P-00079’s conflicting DOBs are still in the files; we surface them.
- **Any … recommendation must expose supporting evidence, confidence/uncertainty, authority requirement and audit metadata** — even though this component is deterministic, the payload shape matches that bar.
- **Separate conventional deterministic engineering from AI-assisted/agentic components** — POC 1 is conventional; it is the substrate an agent may *read*, not a place for the model to invent a merge.
- **Local-first** — no cloud identity graph.

---

## What we deliberately did *not* do

| Temptation | Why we refused | Rule |
|---|---|---|
| Rewrite all 16 MES/QMS conflicting batch rows to match | Those rows are the challenge signal | Do not repair synthetic inconsistencies globally |
| Pick CRM or clinical DOB as “winner” for P-00079 | That fabricates identity | Never fabricate a linkage |
| Auto-fail or auto-release from telemetry / MES | Authority sits with Quality | No autonomous quality-release |
| Add an LLM to “judge” conflicts | Spec: capabilities first, not a chatbot | Deterministic engineering vs agentic |

## Evidence of completion

- `tests/test_legacy_expected_failures.py`: original three assertions preserved; xfail markers removed; strengthening tests added for QC, deviations, consent, review-vs-fail, distinct slot keys.
- `tests/test_patient_reconciliation.py`: aligned IDs, EVAL-002 DOB conflict, duplicate MRN, cross-id collision, unknown id.
- Suite result at conversion: **18 passed**.

## Suggested trainer talking track (90 seconds)

> “The estate did not fail because it lacked an LLM. It failed because three booleans lied.  
> First, `product_ready` treated manufacturing-complete as QA release — we put an explicit QMS state machine in front of that gate, per SOP-QA-014.  
> Second, a single cryogenic point auto-failed a patient-specific shipment under a superseded SOP — we split review from disposition per SOP-LOG-007 v7.  
> Third, a slot retry minted a new UUID and could double-book a suite — we made the command idempotent.  
> Then we added identity reconciliation that *refuses to merge* when CRM and clinical disagree on DOB or when two patients share an MRN.  
> That is FDE: deterministic gates, evidence, human authority. AI can sit on top of this later. It must not replace it.”
