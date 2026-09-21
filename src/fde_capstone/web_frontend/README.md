# CellChain — Control Tower Front End

React client for the governed CAR-T patient-to-batch orchestration layer.

This folder is **self-contained**. It communicates with the backend over HTTP only and holds no
Python imports, no shared build tooling and no relative paths outside itself. Lift the folder into
its own repository and it will run unchanged.

---

## Run

```bash
npm install

npm run dev      # http://localhost:5173, proxies /api to 127.0.0.1:8010
npm run build    # emits dist/, served automatically by the Python service
npm run preview  # preview the production build
```

Point the dev proxy elsewhere with `VITE_API_TARGET`, or build against an absolute API host with
`VITE_API_BASE`:

```bash
VITE_API_TARGET=https://cellchain.internal npm run dev
VITE_API_BASE=https://cellchain.internal npm run build
```

## Structure

```
src/
  main.jsx                 entry point
  App.jsx                  shell: routing, role switching, drawers, notifications
  api/client.js            the only place that talks HTTP
  lib/format.js            status vocabulary, labels, formatting
  styles/theme.css         design system (tokens, layout, components)
  components/
    Logo.jsx               product mark
    Masthead.jsx           global header with role switcher
    SideNav.jsx            navigation + page metadata
    Overlays.jsx           drawer and notification
    ui.jsx                 Panel, Metric, Status, DataTable, Callout, DefinitionList
  pages/
    OperationsDashboard.jsx
    PatientJourney.jsx     fifteen-stage vein-to-vein rail
    ReadinessReview.jsx    cohort readiness list
    ReadinessDetail.jsx    ten gates, facts, actions (drawer)
    ManufacturingSchedule.jsx  slot board + saga detail
    ShipmentTracking.jsx   fleet board + custody, telemetry (drawer)
    DocumentIntake.jsx     upload and proposal queue
    AiAssistants.jsx       assistant registry + result detail (drawer)
    GovernancePages.jsx    patient identity, document security
    SimplePages.jsx        exception queue, site capacity, audit trail
```

## Separating it from the monorepo

1. Copy this folder out.
2. Set `VITE_API_BASE` to the deployed API origin.
3. Enable CORS on the API for that origin.
4. Deploy `dist/` to any static host.

No other change is required. The Python service serves `dist/` when present purely as a convenience
for local demonstration — it is not a coupling.

---

## Design notes

**Palette** follows the EY corporate style: charcoal `#2E2E38`, signature yellow `#FFE600`, generous
white space, confident typography. Type stack is `EY Interstate` where licensed, falling back to
`Inter` then the platform UI font.

**Status colour is a contract.** Five values, five colours, one meaning each, in every view:

| Status | Colour | Meaning |
|---|---|---|
| Pass / Complete | Green | Positive evidence from the authoritative source |
| Fail / Blocked | Red | Known negative |
| Unknown / Needs evidence | Amber | Evidence absent — **not** a failure |
| Conflict | Purple | Authoritative sources disagree |
| Not applicable | Grey | Does not apply at this stage |

**Naming** describes the operational task, not the internal module: *Readiness Review* rather than
`journeys`, *Shipments & Cold Chain* rather than `tracking`, *AI Assistants* rather than `agents`.

**The logo is an original product mark**, not the EY corporate logo. The EY logo is a registered
trademark and is deliberately not reproduced.

### Deliberate omissions

| Omitted | Reason |
|---|---|
| A "Release" button | The affordance must match the authority. Only "Propose for QA review" exists |
| Bulk approval | Consequential actions are per-patient, with evidence |
| Auto-refresh on detail views | An operator must not act on a value that changed silently |
| "Fix this" on a data conflict | Conflicts are evidence; repair belongs in the source system |

### Not yet done

Routing is state-based rather than URL-based, so views are not deep-linkable. There is no test suite
for the client, no accessibility audit, and no internationalisation. Authentication is represented by
a role header for demonstration; a real identity provider is required before deployment.
