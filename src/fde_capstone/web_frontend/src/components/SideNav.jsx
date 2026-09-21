/**
 * Navigation.
 *
 * Names describe the operational task, not the internal module. Grouping follows what an
 * operator is doing: watching the estate, acting on a journey, resolving ambiguity,
 * or proving the system behaved.
 */
export const NAV_SECTIONS = [
  {
    group: 'Monitor',
    items: [
      { id: 'dashboard', label: 'Operations Dashboard', icon: '▤',
        title: 'Operations Dashboard',
        eyebrow: 'Monitor',
        lede: 'Governed readiness across the patient cohort, compared against what the legacy rule asserts. This layer interprets the source systems; it does not overwrite them.' },
      { id: 'journey', label: 'Patient Journey', icon: '⇥',
        title: 'Patient Journey Tracker',
        eyebrow: 'Monitor',
        lede: 'The fifteen vein-to-vein stages for a single patient, each derived from evidence and the readiness gates. A stage is never shown complete on the word of an advisory system.' },
      { id: 'timeline', label: 'Patient Timeline', icon: '◷',
        title: 'Patient Timeline & Forecast',
        eyebrow: 'Monitor',
        lede: 'The plain-language view a patient can be shown: what has happened, how long each step took against the usual, and an advisory interval for the steps still to come. Estimates, never appointments.' },
      { id: 'planner', label: 'Journey Planner', icon: '⏱',
        title: 'New Patient Journey Planner',
        eyebrow: 'Monitor',
        lede: 'Before anyone is enrolled: the journey a patient starting on a chosen date would be expected to have, played out step by step from this estate\u2019s own history. A planning aid, never a schedule.' },
      { id: 'readiness', label: 'Readiness Review', icon: '◎',
        title: 'Readiness Review',
        eyebrow: 'Monitor',
        lede: 'Every patient with the governed readiness verdict beside the legacy status, so divergence is visible per row. Readiness is computed by the deterministic gate engine.' },
      { id: 'exceptions', label: 'Exception Queue', icon: '▲',
        title: 'Exception Queue',
        eyebrow: 'Monitor',
        lede: 'Open exceptions ranked by patient impact and time-criticality rather than by severity label alone. Reordering a worklist changes nothing about authority.' },
    ],
  },
  {
    group: 'Act',
    items: [
      { id: 'onboarding', label: 'Patient Onboarding', icon: '⊞',
        title: 'Patient Onboarding',
        eyebrow: 'Act',
        requires: ['register_patient', 'adjudicate_registration'],
        lede: 'Register a patient the source systems do not know about yet. The record is provisional and carries its own identifier; if the details match someone already in the estate it is held for identity adjudication rather than created.' },
      { id: 'schedule', label: 'Manufacturing Schedule', icon: '▦',
        title: 'Manufacturing Schedule',
        eyebrow: 'Act',
        lede: 'A slot is confirmed only when the scheduler and MES agree. Proposals reserve nothing; a named planner approves, and the workflow compensates automatically if MES rejects.' },
      { id: 'shipments', label: 'Courier Tracking', icon: '➤',
        title: 'Courier Tracking & Cold Chain',
        eyebrow: 'Act',
        lede: 'Carrier performance, custody chain and cryogenic telemetry for every shipment. Disposition of any temperature excursion remains with Quality under SOP-LOG-007 v7.' },
      { id: 'intake', label: 'Document Intake', icon: '⇪',
        title: 'Document Intake',
        eyebrow: 'Act',
        lede: 'Upload correspondence, QC reports, courier manifests or chain-of-identity evidence. Content is untrusted on arrival and becomes evidence only when the named authority confirms it.' },
    ],
  },
  {
    group: 'Resolve',
    items: [
      { id: 'identity', label: 'Patient Identity', icon: '⊘',
        title: 'Patient Identity & Chain of Identity',
        eyebrow: 'Resolve',
        lede: 'A conflicting date of birth or medical record number is never merged automatically. There is no confidence threshold high enough, because one wrong merge is a wrong-patient infusion.' },
      { id: 'capacity', label: 'Site Capacity', icon: '◫',
        title: 'Site Capacity',
        eyebrow: 'Resolve',
        lede: 'Manufacturing site load, phantom capacity where the scheduler and MES disagree, and scheduling decisions taken outside the system of record.' },
    ],
  },
  {
    group: 'Govern',
    items: [
      { id: 'assistants', label: 'AI Assistants', icon: '◈',
        title: 'AI Assistants',
        eyebrow: 'Govern',
        lede: 'AI interprets, explains, retrieves, summarizes, forecasts and proposes. Deterministic gates enforce policy. Authorized humans make consequential decisions.' },
      { id: 'security', label: 'Document Security', icon: '⚿',
        title: 'Document Security',
        eyebrow: 'Govern',
        lede: 'Retrieved content is untrusted data and can never become an instruction. The extractor holds no tools and no write capability, so a successful injection still produces only a proposal.' },
      { id: 'audit', label: 'Audit Trail', icon: '⎘',
        title: 'Audit Trail',
        eyebrow: 'Govern',
        lede: 'Every access is logged with role, purpose and the fields withheld. Every decision records its SOP version, rule version, evidence, required authority and approver.' },
    ],
  },
];

export const PAGES = Object.fromEntries(
  NAV_SECTIONS.flatMap((section) => section.items.map((item) => [item.id, item])),
);

/** A page is offered only if the role can do something on it. Read-only pages carry no rule. */
export function allowsPage(item, can) {
  return !item.requires || item.requires.some((action) => can(action));
}

export default function SideNav({
  activePage, onNavigate, can, open = false, collapsed = false, onToggleCollapse, badges = {},
}) {
  return (
    <nav
      className={`sidenav${open ? ' sidenav--open' : ''}${collapsed ? ' sidenav--collapsed' : ''}`}
      aria-label="Primary"
    >
      <div className="sidenav__scroll">
        {NAV_SECTIONS.map((section) => {
          const items = section.items.filter((item) => allowsPage(item, can));
          if (!items.length) return null;
          return (
            <div key={section.group} className="sidenav__section">
              <div className="sidenav__group" aria-hidden={collapsed}>{section.group}</div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`sidenav__item${activePage === item.id ? ' sidenav__item--active' : ''}`}
                  onClick={() => onNavigate(item.id)}
                  aria-current={activePage === item.id ? 'page' : undefined}
                  aria-label={item.label}
                  data-tip={item.label}
                >
                  <span className="sidenav__icon" aria-hidden="true">{item.icon}</span>
                  <span className="sidenav__label">{item.label}</span>
                  {badges[item.id] ? <span className="sidenav__badge">{badges[item.id]}</span> : null}
                </button>
              ))}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        className="sidenav__collapse"
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
      >
        <span className="sidenav__collapse-icon" aria-hidden="true">‹</span>
        <span className="sidenav__label">Collapse</span>
      </button>
    </nav>
  );
}
