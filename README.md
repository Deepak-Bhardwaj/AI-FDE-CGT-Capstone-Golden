# FDE Final Capstone

This repository is a built **synthetic academic** Cell and Gene Therapy patient-to-batch orchestration demonstration. All 21 AI FDE stages have documented artifacts, but owner approvals, independently assured outputs, real-system deployment and observed business benefits are not implied.

> **Start here:** [Client ask and end-to-end demo](docs/CLIENT_ASK_AND_END_TO_END_DEMO.md) · [Ten-deliverable acceptance matrix](docs/CLIENT_DELIVERABLE_ACCEPTANCE_MATRIX.md) · [Final report](docs/FINAL_CAPSTONE_REPORT.md) · [One-to-one 21-stage artifact register](docs/21_STAGE_ARTIFACT_REGISTER.md) · [Documentation hub](docs/README.md) · [Demo guide](docs/DEMO_GUIDE.md)

## What it solves

The inherited environment had conflicting patient evidence, unsafe readiness/release shortcuts, weak retry handling and fragmented exception work. This solution provides one evidence-driven orchestration layer with:

- source-specific assertions and bitemporal history;
- explicit satisfied/not-satisfied/unknown outcomes;
- human-authorized identity and Quality decisions;
- safe idempotent commands and reconciliation;
- owned exceptions and tamper-evident audit;
- three integrated POCs;
- six read-only original v2 source-timestamp patient journeys and non-authoritative disruption preview;
- seven role/persona demo lenses across Patient Operations, Identity, Logistics/Planning, Manufacturing, Lab/QC, Quality and Executive views;
- an automated deterministic cross-domain journey summary and visible workflow-automation trace;
- one optional recommendation-only assistant, disabled by default.

## Important boundary

This is not a production, clinical, regulatory or validated system. It uses synthetic data and simulated authorities/integrations. No live AI model is included. The final lifecycle decision is **restrict and change**: accept the academic POC, keep AI off and do not pilot with real data until the seven CAPAs in Stage 20 are closed.

## Repository layout

| Path | Purpose |
|---|---|
| [`src/fde_capstone`](src/fde_capstone) | Application, services, adapters, API, CLI and browser frontend |
| [`docs`](docs/README.md) | Final report, plan, progress, traceability, demo guide and documentation index |
| [`docs/stages`](docs/stages/README.md) | Academic stage folders; the artifact register states each PDF and merged-capability status |
| [`requirements`](requirements) | Requirements and machine-readable verification/traceability matrices |
| [`evidence`](evidence) | Local academic repository-verification result; not independent assurance |
| [`reports`](reports) | Generated JUnit test evidence |
| [`tests`](tests) | Unit, integration, end-to-end, recovery and performance tests |
| [`tools`](tools) | Reproducible evidence, evaluation and verification utilities |
| [`source_baseline`](source_baseline) | Frozen 132-file challenge extraction; do not modify |

## Browser demonstration

On macOS, double-click `START_DEMO.command`, keep its terminal window open, and use the Control Tower page that opens automatically. The browser executes all three POCs against isolated synthetic state; it is not a disconnected mockup.

Alternatively, start it from a terminal:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,api]'
FDE_DB=runtime/control-tower.db AI_MODE=off PYTHONPATH=src \
  .venv/bin/python -m uvicorn fde_capstone.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> for the Control Tower and <http://127.0.0.1:8000/docs> for the API. See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the presentation sequence. The three-POC scripted fixture is separate from the six frozen v2 source-timestamp journeys and inject preview.

## Results

- 106 local automated tests passed with 95.89% source coverage.
- 57 evaluation cases executed: 55 internal **structural** passes, 0 failures and 2 human-study cases inconclusive. Only 7 original cases have full scoped property assertions, 9 are partial, and 39 extension cases are structural probes only.
- 29/31 requirements are internally verified; zero are production verified. The registered 20-client/27,507-row journey-projection NFR remains unverified.
- 20/20 simulated shadow comparisons matched.
- 10/10 simulated canary journeys succeeded.
- Backup/restore and AI-off rollback passed locally.
- Original ZIP and all 132 extracted evidence files remained unchanged; the attached v2 directory matches the frozen baseline byte-for-byte (ignoring `.DS_Store`).

## CLI and evaluation

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,api]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
.venv/bin/mypy src
PYTHONPATH=src .venv/bin/python -m fde_capstone.cli demo --db runtime/demo.db
PYTHONPATH=src .venv/bin/python -m fde_capstone.cli evaluate --db runtime/eval.db --output reports/evaluation.json
```

The local `runtime/` folder contains disposable synthetic state. Stop the demo server before cleaning it; do not delete unrelated user files.

### Mutating demo API authentication

The slot-reservation API no longer trusts caller-supplied role headers. Configure opaque bearer
tokens and their fixed server-side demo identities with `FDE_DEMO_IDENTITIES_JSON`; without that
configuration, mutating routes fail closed with HTTP 503. See `.env.example`. The browser's
read-only status/source views and isolated three-POC demo do not require a mutation token.

## Verification provenance

Local verification directly hashes the original external ZIP when it is available at its recorded path. GitHub Actions intentionally does not receive that external archive; it verifies the recorded ZIP digest plus all 132 committed frozen extraction files against their individual inventory hashes. Generated package metadata such as `*.egg-info` is excluded from the signed application-source digest.

For the requested training sequence, use [the six source-journey reconstructions](docs/stages/stage_02/07_SUPPLIED_PATIENT_JOURNEY_SOURCE_RECONSTRUCTION.md), [PRD](docs/stages/stage_13/06_PRODUCT_REQUIREMENTS_DOCUMENT.md), [product-to-code-test-demo trace](docs/stages/stage_13/07_PRODUCT_TO_CODE_TEST_DEMO_TRACE.md), [target C4](docs/stages/stage_10/05_TARGET_C4_BASELINE_AND_AS_BUILT_DELTA.md), [migration strategy](docs/stages/stage_13/08_BROWNFIELD_MIGRATION_STRATEGY.md), and [90-day production-gap roadmap](docs/stages/stage_20/06_PRODUCTION_GAP_AND_90_DAY_ROADMAP.md).

## Information retrieval and integration position

Authoritative operational facts use typed adapters, the evidence registry and deterministic projections; canonical state is not produced by vector RAG. Optional future RAG is appropriate for supporting unstructured SOP/email/deviation content only, with provenance, version/freshness and citations. MCP is not required by the current POC; it is a future enterprise integration option for approved read/tool adapters after identity, authorization, audit and supplier controls are satisfied.
