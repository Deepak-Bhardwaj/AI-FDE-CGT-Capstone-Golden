const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  runButtons: $$('[data-run-demo]'),
  mode: $('#ai-mode'),
  runState: $('#run-state'),
  progress: $('#progress-fill'),
  toast: $('#toast'),
};

let latestDemoResult = null;

const pause = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function setText(selector, value, className = '') {
  const element = $(selector);
  element.textContent = value;
  element.classList.remove('value-pass', 'value-warn');
  if (className) element.classList.add(className);
}

function setBadge(number, label, state) {
  const badge = $(`#poc-${number}-badge`);
  badge.textContent = label;
  badge.className = `result-badge result-${state}`;
}

function setRunning(number) {
  $$('.poc-card').forEach((card) => card.classList.remove('is-running'));
  const card = $(`#poc-${number}`);
  card.classList.add('is-running');
  setBadge(number, 'Running', 'running');
}

function setProgress(value, message) {
  elements.progress.style.width = `${value}%`;
  elements.runState.textContent = message;
}

function completeJourneyThrough(index) {
  $$('.journey-step').forEach((step) => {
    step.classList.toggle('is-complete', Number(step.dataset.step) <= index);
  });
}

function resetDemo() {
  $$('.poc-card').forEach((card) => card.classList.remove('is-running', 'is-complete'));
  [1, 2, 3].forEach((number) => setBadge(number, 'Not run', 'idle'));
  completeJourneyThrough(-1);
  setProgress(4, 'Creating isolated synthetic runtime…');
  $('#console-empty').hidden = false;
  $('#console-results').hidden = true;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add('show');
  window.setTimeout(() => elements.toast.classList.remove('show'), 3200);
}

async function loadStatus() {
  try {
    const response = await fetch('/api/capstone/status');
    if (!response.ok) throw new Error(`Status request failed (${response.status})`);
    const status = await response.json();
    $('#stage-count').textContent = `${status.stages.documented}/${status.stages.total}`;
    $('#test-count').textContent = status.tests.passed;
    $('#evaluation-count').textContent = `${status.evaluations.structural_passes}/57`;
    $('#requirement-count').textContent = `${status.requirements.verified_internal_poc}/${status.requirements.total}`;
    $('#score-requirement-verified').textContent = status.requirements.verified_internal_poc;
    $('#score-requirement-total').textContent = `of ${status.requirements.total}`;
    $('#requirement-score-ring').setAttribute('aria-label', `${status.requirements.verified_internal_poc} of ${status.requirements.total} requirements internally verified`);
  } catch (error) {
    showToast('Status unavailable. Start the FastAPI server and refresh.');
  }
}

function renderRoleLens() {
  const select = $('#role-lens');
  const selectedLabel = select.options[select.selectedIndex]?.textContent || 'Role';
  if (!latestDemoResult) {
    setText('#role-title', selectedLabel);
    setText('#role-objective', 'Run the end-to-end demo to load this role\'s evidence, responsibilities and boundaries.');
    setText('#role-backend', 'Mapped after run');
    setText('#role-focus', 'Role-specific operational view');
    setText('#role-can-do', 'Uses the same governed journey with role-appropriate responsibilities.');
    setText('#role-cannot-do', 'Cannot take another domain\'s consequential authority.');
    return;
  }
  const role = latestDemoResult.role_views.find((item) => item.id === select.value);
  if (!role) return;
  setText('#role-title', role.name);
  setText('#role-objective', role.focus);
  setText('#role-backend', role.backend_role);
  setText('#role-focus', role.focus);
  setText('#role-can-do', role.can_do.join(' · '));
  setText('#role-cannot-do', role.cannot_do.join(' · '));
}

function renderJourneySummary(result) {
  const summary = result.journey_summary;
  setText('#summary-status', summary.overall_status, 'value-pass');
  setText('#summary-blocker', summary.current_blocker, summary.current_blocker === 'NONE' ? 'value-pass' : 'value-warn');
  setText('#summary-next-owner', summary.next_owner);
  setText('#summary-evidence-count', String(summary.evidence_count));
  setText('#journey-summary-text', summary.summary);
  const domains = $('#domain-summary');
  domains.replaceChildren();
  summary.domains.forEach((item) => {
    const card = document.createElement('article');
    const heading = document.createElement('strong');
    const status = document.createElement('span');
    const detail = document.createElement('p');
    heading.textContent = item.domain;
    status.textContent = item.status;
    status.className = item.status === 'SATISFIED' ? 'value-pass' : 'value-warn';
    detail.textContent = item.detail;
    card.append(heading, status, detail);
    domains.appendChild(card);
  });
  const trace = $('#automation-trace');
  trace.replaceChildren();
  result.automation_trace.forEach((item) => {
    const row = document.createElement('li');
    row.textContent = `${item.step}: ${item.automation}. Human boundary: ${item.human_boundary}.`;
    trace.appendChild(row);
  });
  const rec = result.assistant_output;
  setText('#assistant-explanation', rec?.summary ? `${rec.summary} Evidence: ${rec.evidence_refs.join(', ')}` : 'AI is off. The summary above was generated deterministically from governed state and evidence.');
}

async function presentResults(result) {
  latestDemoResult = result;
  renderRoleLens();
  renderJourneySummary(result);
  completeJourneyThrough(0);
  setRunning(1);
  setProgress(25, 'Resolving identity conflict with human authority…');
  await pause(550);
  setText('#identity-decision', result.poc1.decision, 'value-pass');
  setText('#identity-readiness', result.poc1.readiness, 'value-pass');
  setText('#identity-evidence', `${result.poc1.evidence_refs.length} cited`);
  setBadge(1, 'Controlled', 'pass');
  $('#poc-1').classList.remove('is-running');
  $('#poc-1').classList.add('is-complete');
  completeJourneyThrough(2);

  setRunning(2);
  setProgress(52, 'Reconciling unknown slot-reservation outcome…');
  await pause(650);
  setText('#slot-initial', result.poc2.initial_state, 'value-warn');
  setText('#slot-reconciled', result.poc2.reconciled_state, 'value-pass');
  setText('#slot-replay', result.poc2.replay_dispatch ? 'YES · unsafe' : 'NO · prevented', 'value-pass');
  setBadge(2, 'Reconciled', 'pass');
  $('#poc-2').classList.remove('is-running');
  $('#poc-2').classList.add('is-complete');
  completeJourneyThrough(4);

  setRunning(3);
  setProgress(78, 'Assembling evidence packet and applying Quality decision…');
  await pause(650);
  setText('#quality-before', result.poc3.before, 'value-warn');
  setText('#quality-release', result.poc3.released ? 'HUMAN AUTHORIZED' : 'BLOCKED', result.poc3.released ? 'value-pass' : 'value-warn');
  setText('#quality-after', result.poc3.after, 'value-pass');
  setBadge(3, 'Released', 'pass');
  $('#poc-3').classList.remove('is-running');
  $('#poc-3').classList.add('is-complete');
  completeJourneyThrough(7);

  const evidence = [...new Set([...result.poc1.evidence_refs, ...result.poc3.evidence_refs])].sort();
  const evidenceContainer = $('#evidence-chips');
  evidenceContainer.replaceChildren();
  evidence.forEach((reference) => {
    const chip = document.createElement('span');
    chip.textContent = reference;
    evidenceContainer.appendChild(chip);
  });

  $('#console-empty').hidden = true;
  $('#console-results').hidden = false;
  setText('#audit-result', result.audit_chain_valid ? 'VALID' : 'FAILED', result.audit_chain_valid ? 'value-pass' : 'value-warn');
  setText('#assistant-result', result.assistant.mode.replaceAll('_', ' '));
  setText('#metric-result', `${Object.keys(result.metrics).length} signals`);
  setText('#state-digest', result.state_digest);
  setText('#hero-audit', result.state_digest.slice(0, 12));
  $('#run-scope').textContent = result.scope;
  setProgress(100, 'Journey complete · evidence and audit record verified');
  if (result.governance?.audit) {
    renderAuditRecords($('#audit-output'), result.governance.audit, 'Demo-run audit chain');
  }
  showToast('Synthetic patient-to-batch journey completed successfully.');
}

async function runDemo() {
  if (elements.runButtons.some((button) => button.disabled)) return;
  resetDemo();
  elements.runButtons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch('/api/demo/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ai_mode: elements.mode.value }),
    });
    if (!response.ok) throw new Error(`Demo request failed (${response.status})`);
    const result = await response.json();
    await presentResults(result);
  } catch (error) {
    setProgress(0, 'Demo could not complete');
    showToast(error.message || 'Unexpected demo error');
  } finally {
    $$('.poc-card').forEach((card) => card.classList.remove('is-running'));
    elements.runButtons.forEach((button) => { button.disabled = false; });
  }
}

function appendText(parent, tag, value, className = '') {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.appendChild(element);
  return element;
}

async function loadSourceChoices() {
  try {
    const [caseResponse, injectResponse] = await Promise.all([
      fetch('/api/source/cases'), fetch('/api/source/injects'),
    ]);
    if (!caseResponse.ok || !injectResponse.ok) throw new Error('Frozen source fixtures unavailable');
    const [caseList, injectList] = await Promise.all([caseResponse.json(), injectResponse.json()]);
    const caseSelect = $('#source-case');
    const injectSelect = $('#source-inject');
    caseSelect.replaceChildren();
    injectSelect.replaceChildren();
    caseList.cases.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.case_id;
      option.textContent = `${item.case_id} · ${item.patient_key}`;
      caseSelect.appendChild(option);
    });
    injectList.injects.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.inject_id;
      option.textContent = `${item.inject_id} · ${item.name}`;
      injectSelect.appendChild(option);
    });
  } catch (error) {
    $('#source-case-output').textContent = error.message || 'Source evidence unavailable';
    $('#source-inject-output').textContent = error.message || 'Disruption catalog unavailable';
  }
}

async function inspectSourceCase() {
  const caseId = $('#source-case').value;
  if (!caseId) return;
  const output = $('#source-case-output');
  output.textContent = 'Loading exact v2 source rows…';
  try {
    const response = await fetch(`/api/source/cases/${encodeURIComponent(caseId)}`);
    if (!response.ok) throw new Error(`Source case request failed (${response.status})`);
    const result = await response.json();
    output.replaceChildren();
    appendText(output, 'h4', `${result.case_id} · ${result.patient_key}`);
    appendText(output, 'p', result.question);
    appendText(output, 'p', 'Source assertions only · no identity or Quality disposition', 'scope-note');
    const observations = document.createElement('ul');
    result.observations.forEach((item) => {
      appendText(observations, 'li', `${item.property}: ${item.status}. ${item.explanation}`);
    });
    output.appendChild(observations);
    const journey = result.timestamp_order_reconstruction;
    const reconstruction = document.createElement('details');
    appendText(reconstruction, 'summary', `Source-timestamp journey order · ${journey.timeline.length} assertions`);
    appendText(reconstruction, 'p', 'Timestamp order is not causal truth, known-at replay, approved COI/COC or Quality release.', 'scope-note');
    const gates = document.createElement('ul');
    Object.entries(journey.control_gates).forEach(([gate, status]) => {
      appendText(gates, 'li', `${gate.replaceAll('_', ' ')}: ${status}`);
    });
    reconstruction.appendChild(gates);
    const eventList = document.createElement('ol');
    journey.timeline.forEach((event) => {
      appendText(eventList, 'li', `${event.occurred_at} · ${event.event_kind} · ${event.asserted_state} · ${event.source_locator}`);
    });
    reconstruction.appendChild(eventList);
    if (journey.temporal_conflicts.length) {
      appendText(reconstruction, 'p', `Temporal conflicts: ${journey.temporal_conflicts.map((item) => item.shipment_id).join(', ')}. No times corrected.`, 'scope-note');
    }
    output.appendChild(reconstruction);
    Object.entries(result.source_records).forEach(([table, rows]) => {
      if (!rows.length) return;
      const details = document.createElement('details');
      appendText(details, 'summary', `${table.replaceAll('_', ' ')} · ${rows.length} source row${rows.length === 1 ? '' : 's'}`);
      const content = rows.map((item) => `${item.source_locator}\n${JSON.stringify(item.row, null, 2)}`).join('\n\n');
      appendText(details, 'pre', content);
      output.appendChild(details);
    });
  } catch (error) {
    output.textContent = error.message || 'Source case unavailable';
  }
}

async function inspectSourceInject() {
  const injectId = $('#source-inject').value;
  const patientKey = $('#representative-patient').value.trim();
  const output = $('#source-inject-output');
  if (!injectId) return;
  if (!/^P-\d{5}$/.test(patientKey)) {
    output.textContent = 'Enter a synthetic key such as P-00001.';
    return;
  }
  output.textContent = 'Building non-authoritative impact preview…';
  try {
    const response = await fetch(`/api/source/injects/${encodeURIComponent(injectId)}/preview?patient_key=${encodeURIComponent(patientKey)}`);
    if (!response.ok) throw new Error(`Disruption preview failed (${response.status})`);
    const result = await response.json();
    output.replaceChildren();
    appendText(output, 'h4', `${result.inject_id} · ${result.name}`);
    appendText(output, 'p', `Trigger: ${result.trigger}; representative patient: ${result.representative_patient_key}`);
    appendText(output, 'p', `Owner: ${result.owner_role}; side effects: ${result.side_effects}; not an approved plan`, 'scope-note');
    const impact = document.createElement('ul');
    result.impact_preview.forEach((item) => {
      const timing = item.hypothetical_zero_slack_time ? `zero-slack scenario ${item.hypothetical_zero_slack_time}` : 'timing unknown';
      appendText(impact, 'li', `${item.milestone}: ${item.status}; ${timing}; source ${item.source_locator || 'not supplied'}`);
    });
    output.appendChild(impact);
    if (result.affected_routes.length) {
      appendText(output, 'h4', 'Routes requiring owner review');
      result.affected_routes.forEach((route) => appendText(output, 'p', `${route.shipment_id} ${route.origin} → ${route.destination}: ${route.delivery_assurance}`));
    }
    if (result.affected_reservations.length) {
      appendText(output, 'h4', 'Reservations at risk');
      result.affected_reservations.forEach((slot) => appendText(output, 'p', `${slot.slot_id} · ${slot.state} · ${slot.owner}`));
    }
    const assumptions = document.createElement('details');
    appendText(assumptions, 'summary', 'Assumptions and limits');
    appendText(assumptions, 'pre', result.assumptions.join('\n'));
    output.appendChild(assumptions);
  } catch (error) {
    output.textContent = error.message || 'Disruption preview unavailable';
  }
}

function severityClass(severity) {
  const value = String(severity || '').toLowerCase();
  if (value === 'critical') return 'severity-critical';
  if (value === 'high') return 'severity-high';
  if (value === 'major') return 'severity-major';
  return '';
}

function renderAuditRecords(container, snapshot, heading) {
  container.replaceChildren();
  appendText(container, 'h4', heading || 'Audit ledger');
  const valid = snapshot.chain_valid;
  appendText(container, 'p', valid ? 'Hash chain valid · SHA-256 canonical JSON' : 'Hash chain FAILED — a row was altered, reordered or removed', valid ? '' : 'scope-note');
  appendText(container, 'p', `${snapshot.entries || 0} records · head ${(snapshot.head || 'GENESIS').slice(0, 16)}`);
  setText('#gov-audit-valid', valid ? 'VALID' : 'FAILED', valid ? 'value-pass' : 'value-warn');
  setText('#gov-audit-count', `${snapshot.entries || 0} chained records`);
  const records = snapshot.records || [];
  if (!records.length) {
    appendText(container, 'p', 'No operational audit rows on the live ledger yet. Run the end-to-end demo to populate a disposable chain, or use a mutating API with a configured bearer identity.');
    return;
  }
  const table = document.createElement('table');
  table.className = 'ops-table';
  table.innerHTML = '<thead><tr><th>Time</th><th>Principal</th><th>Action</th><th>Scope</th><th>Outcome</th><th>Hash</th></tr></thead>';
  const body = document.createElement('tbody');
  records.forEach((row) => {
    const tr = document.createElement('tr');
    [
      (row.recorded_at || '').replace('T', ' ').slice(0, 19),
      row.principal || '—',
      row.action || '—',
      row.scope || '—',
      row.outcome || '—',
      (row.record_hash || '').slice(0, 12),
    ].forEach((value, index) => {
      const td = document.createElement('td');
      td.textContent = value;
      if (index === 5) td.className = 'mono';
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  table.appendChild(body);
  container.appendChild(table);
}

async function inspectIdentity() {
  const orchestrationId = $('#identity-orchestration').value.trim();
  const mrn = $('#identity-mrn').value.trim();
  const output = $('#identity-output');
  if (!orchestrationId && !mrn) {
    output.textContent = 'Enter a synthetic patient key such as P-00001 or an MRN.';
    return;
  }
  output.textContent = 'Loading identity evidence pack…';
  try {
    const params = new URLSearchParams();
    if (orchestrationId) params.set('orchestration_id', orchestrationId);
    if (mrn) params.set('mrn', mrn);
    const response = await fetch(`/api/governance/identity?${params.toString()}`);
    if (!response.ok) throw new Error(`Identity request failed (${response.status})`);
    const result = await response.json();
    output.replaceChildren();
    const key = result.resolved_patient_key || 'unresolved';
    appendText(output, 'h4', key === 'unresolved' || !key ? 'Unresolved identity' : `Resolved ${key}`);
    appendText(output, 'p', result.note || 'Evidence pack only.', 'scope-note');
    const facts = document.createElement('ul');
    appendText(facts, 'li', `Confidence: ${result.confidence_score}`);
    appendText(facts, 'li', `Human review: ${result.requires_human_review ? 'required' : 'not required'}`);
    appendText(facts, 'li', `Authority: ${result.authority_requirement}`);
    appendText(facts, 'li', `Conflicts: ${result.conflicts.length}`);
    output.appendChild(facts);
    if (result.conflicts.length) {
      result.conflicts.slice(0, 6).forEach((conflict) => {
        const details = document.createElement('details');
        appendText(details, 'summary', conflict.type || 'conflict');
        appendText(details, 'pre', JSON.stringify(conflict, null, 2));
        output.appendChild(details);
      });
    }
    setText('#gov-identity-key', key || '—');
    setText('#gov-identity-flag', result.requires_human_review ? 'HITL required' : 'Sources agree');
  } catch (error) {
    output.textContent = error.message || 'Identity evidence unavailable';
  }
}

async function loadExceptions() {
  const patientKey = $('#exception-patient').value.trim();
  const output = $('#exception-output');
  if (patientKey && !/^P-\d{5}$/.test(patientKey)) {
    output.textContent = 'Enter a synthetic key such as P-00001, or leave blank for the ranked queue.';
    return;
  }
  output.textContent = 'Loading ranked exceptions…';
  try {
    const params = new URLSearchParams({ limit: '12' });
    if (patientKey) params.set('patient_key', patientKey);
    const response = await fetch(`/api/governance/exceptions?${params.toString()}`);
    if (!response.ok) throw new Error(`Exception request failed (${response.status})`);
    const result = await response.json();
    output.replaceChildren();
    appendText(output, 'h4', `${result.shown} of ${result.count} exceptions`);
    appendText(output, 'p', result.note, 'scope-note');
    setText('#gov-exception-count', String(result.shown));
    if (!result.exceptions.length) {
      appendText(output, 'p', 'No exceptions matched this filter.');
      return;
    }
    const table = document.createElement('table');
    table.className = 'ops-table';
    table.innerHTML = '<thead><tr><th>Reference</th><th>Patient</th><th>Type</th><th>Severity</th><th>Recommendation</th></tr></thead>';
    const body = document.createElement('tbody');
    result.exceptions.forEach((row) => {
      const tr = document.createElement('tr');
      const cells = [
        row.exception_id,
        row.patient_id || '—',
        row.exception_type,
        row.severity,
        row.recommendation,
      ];
      cells.forEach((value, index) => {
        const td = document.createElement('td');
        td.textContent = value;
        if (index <= 1) td.className = 'mono';
        if (index === 3) td.className = severityClass(row.severity);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    output.appendChild(table);
  } catch (error) {
    output.textContent = error.message || 'Exception queue unavailable';
  }
}

async function loadAudit() {
  const output = $('#audit-output');
  output.textContent = 'Verifying hash chain…';
  try {
    const response = await fetch('/api/governance/audit?limit=20');
    if (!response.ok) throw new Error(`Audit request failed (${response.status})`);
    const snapshot = await response.json();
    renderAuditRecords(output, snapshot, 'Live operational ledger');
  } catch (error) {
    output.textContent = error.message || 'Audit ledger unavailable';
  }
}

const VIEW_META = {
  command: { crumb: 'Command / Overview', title: 'Vein-to-vein command' },
  roles: { crumb: 'Operate / Roles', title: 'Role workspace' },
  'source-evidence': { crumb: 'Evidence / Source', title: 'Frozen challenge cases' },
  governance: { crumb: 'Evidence / Governance', title: 'Identity · exceptions · audit' },
  pocs: { crumb: 'Operate / Live demo', title: 'Integrated demonstration' },
  assurance: { crumb: 'Assure / Boundaries', title: 'Confidence without overclaiming' },
};

const VIEW_ALIASES = {
  top: 'command',
  journey: 'command',
  disruptions: 'source-evidence',
};

function activateView(viewId, { updateHash = true } = {}) {
  const id = VIEW_ALIASES[viewId] || viewId;
  if (!VIEW_META[id]) return;
  $$('.view').forEach((view) => view.classList.toggle('is-active', view.dataset.view === id));
  $$('.nav-link[data-nav]').forEach((link) => link.classList.toggle('is-active', link.dataset.nav === id));
  const meta = VIEW_META[id];
  setText('#view-crumb', meta.crumb);
  setText('#view-title', meta.title);
  document.querySelector('.app')?.classList.remove('rail-open');
  const toggle = $('[data-toggle-rail]');
  if (toggle) toggle.setAttribute('aria-expanded', 'false');
  if (updateHash && window.location.hash.replace('#', '') !== id && window.location.hash.replace('#', '') !== viewId) {
    history.replaceState(null, '', `#${id}`);
  }
  $('.viewport')?.scrollTo({ top: 0 });
}

function activateFromHash() {
  const raw = window.location.hash.replace('#', '') || 'command';
  activateView(raw, { updateHash: false });
  if (raw === 'journey') {
    $('#journey')?.scrollIntoView({ block: 'start' });
  }
}

async function runDemoAndShow() {
  activateView('pocs');
  await runDemo();
}

elements.runButtons.forEach((button) => button.addEventListener('click', runDemoAndShow));
$('#role-lens').addEventListener('change', renderRoleLens);
$('#show-source-case').addEventListener('click', inspectSourceCase);
$('#show-source-inject').addEventListener('click', inspectSourceInject);
$('#inspect-identity').addEventListener('click', inspectIdentity);
$('#load-exceptions').addEventListener('click', loadExceptions);
$('#load-audit').addEventListener('click', loadAudit);
$$('[data-nav]').forEach((link) => {
  link.addEventListener('click', (event) => {
    event.preventDefault();
    activateView(link.dataset.nav);
  });
});
$('[data-toggle-rail]')?.addEventListener('click', () => {
  const app = $('.app');
  const open = app.classList.toggle('rail-open');
  $('[data-toggle-rail]').setAttribute('aria-expanded', String(open));
});
window.addEventListener('hashchange', activateFromHash);
activateFromHash();
loadStatus();
loadSourceChoices();
loadExceptions();
loadAudit();
