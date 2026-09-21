import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DataTable, Loading, Panel, Status } from '../components/ui';
import { hours, label } from '../lib/format';

export function ExceptionQueue() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get('/api/exceptions?limit=25').then((r) => setData(r.data)); }, []);
  if (!data) return <Loading />;

  return (
    <Panel title="Open exceptions" note={data.method} flush>
      <DataTable
        columns={[
          { key: 'exception_id', header: 'Reference', render: (r) => <span className="mono">{r.exception_id}</span> },
          { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono">{r.patient_key || '—'}</span> },
          { key: 'kind', header: 'Type', render: (r) => label(r.kind.split(':').pop()) },
          { key: 'score', header: 'Impact score', align: 'right', render: (r) => <strong style={{ color: 'var(--fail)' }}>{r.score}</strong> },
          { key: 'age_hours', header: 'Open for', align: 'right', render: (r) => (r.age_hours ? hours(r.age_hours) : '—') },
          { key: 'owner', header: 'Owner', render: (r) => (r.owner ? r.owner : <Status value="FAIL">Unassigned</Status>) },
          { key: 'authority', header: 'Authority', render: (r) => <span className="muted">{r.authority}</span> },
          { key: 'drivers', header: 'Why it ranks here', render: (r) => <span className="subtle">{r.drivers.join(' · ')}</span> },
        ]}
        rows={data.exceptions.map((e) => ({ ...e, id: e.exception_id }))}
      />
    </Panel>
  );
}

export function SiteCapacity() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get('/api/capacity').then((r) => setData(r.data)); }, []);
  if (!data) return <Loading />;

  return (
    <>
      <Panel title="Manufacturing sites" note="Booked slots against declared suite and QC throughput." flush>
        <DataTable
          columns={[
            { key: 'name', header: 'Site', render: (r) => (<><div>{r.name}</div><div className="mono subtle">{r.site_id}</div></>) },
            { key: 'country', header: 'Country' },
            { key: 'suites', header: 'Suites', align: 'right' },
            { key: 'qc_capacity_day', header: 'QC per day', align: 'right' },
            { key: 'booked', header: 'Slots booked', align: 'right', render: (r) => <span className="mono">{r.booked}</span> },
          ]}
          rows={data.sites.map((s) => ({ ...s, id: s.site_id }))}
        />
      </Panel>

      <Panel
        title="Phantom capacity"
        note="Slots the scheduler reports as confirmed while MES has cancelled them. Capacity that exists on paper and not in the plant."
        flush
      >
        <DataTable
          columns={[
            { key: 'slot_id', header: 'Slot', render: (r) => <span className="mono">{r.slot_id}</span> },
            { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono">{r.patient_key}</span> },
            { key: 'scheduler_state', header: 'Scheduler', render: (r) => <Status value="PASS">{label(r.scheduler_state)}</Status> },
            { key: 'mes_state', header: 'MES', render: (r) => <Status value="FAIL">{label(r.mes_state)}</Status> },
          ]}
          rows={data.phantom_capacity.map((s) => ({ ...s, id: s.slot_id }))}
          empty="No phantom capacity detected."
        />
      </Panel>

      <Panel
        title="Scheduling decisions taken outside the system"
        note={`${data.shadow_drift_total} slots differ from the offline planning spreadsheet.`}
        flush
      >
        <DataTable
          columns={[
            { key: 'slot_id', header: 'Slot', render: (r) => <span className="mono">{r.slot_id}</span> },
            { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono">{r.patient_key}</span> },
            { key: 'system_priority', header: 'System priority', align: 'right', render: (r) => <span className="mono">{r.system_priority}</span> },
            { key: 'shadow_priority', header: 'Spreadsheet priority', align: 'right', render: (r) => <Status value="CONFLICT">{r.shadow_priority}</Status> },
            { key: 'planner_note', header: 'Planner note', render: (r) => <span className="muted">{r.planner_note || '—'}</span> },
          ]}
          rows={data.shadow_drift.map((s) => ({ ...s, id: s.slot_id }))}
          empty="No drift detected."
        />
      </Panel>
    </>
  );
}

export function AuditTrail() {
  const [access, setAccess] = useState(null);
  const [decisions, setDecisions] = useState(null);

  useEffect(() => {
    api.get('/api/audit/access?limit=40').then((r) => setAccess(r.data));
    api.get('/api/audit/decisions?limit=20').then((r) => setDecisions(r.data));
  }, []);

  if (!access || !decisions) return <Loading />;

  return (
    <>
      <Panel title="Access log" note={`${access.total} access decisions recorded this session.`} flush>
        <DataTable
          columns={[
            { key: 'at', header: 'Time', render: (r) => <span className="mono">{r.at.slice(11, 19)}</span> },
            { key: 'identity', header: 'Identity', render: (r) => <span className="mono">{r.identity}</span> },
            { key: 'role', header: 'Role', render: (r) => label(r.role) },
            { key: 'purpose', header: 'Purpose', render: (r) => <span className="subtle">{label(r.purpose)}</span> },
            { key: 'action', header: 'Action', render: (r) => <span className="mono">{r.action}</span> },
            { key: 'subject', header: 'Subject', render: (r) => <span className="mono">{r.subject}</span> },
            { key: 'allowed', header: 'Outcome', render: (r) => <Status value={r.allowed ? 'PASS' : 'FAIL'}>{r.allowed ? 'Allowed' : 'Denied'}</Status> },
          ]}
          rows={access.entries.map((e, i) => ({ ...e, id: i }))}
        />
      </Panel>

      <Panel title="Decision log" note={`${decisions.total} decisions, each bound to the rule version that produced it.`} flush>
        <DataTable
          columns={[
            { key: 'decision_id', header: 'Reference', render: (r) => <span className="mono">{r.decision_id.slice(0, 14)}</span> },
            { key: 'subject', header: 'Patient', render: (r) => <span className="mono">{r.subject.patient_key || '—'}</span> },
            { key: 'action', header: 'Action', render: (r) => <span className="mono">{r.action}</span> },
            { key: 'action_class', header: 'Authority class', render: (r) => <Status value={r.action_class === 'D' ? 'FAIL' : 'UNKNOWN'}>Class {r.action_class}</Status> },
            { key: 'recommendation', header: 'Recommendation', render: (r) => label(r.recommendation) },
            { key: 'rule', header: 'Rule', render: (r) => <span className="mono">{r.rule.sop_id || '—'} {r.rule.sop_version || ''}</span> },
            { key: 'approved_by', header: 'Approved by', render: (r) => (r.approved_by ? r.approved_by : <span className="subtle">Not approved</span>) },
          ]}
          rows={decisions.entries.map((e, i) => ({ ...e, id: i }))}
        />
      </Panel>
    </>
  );
}
