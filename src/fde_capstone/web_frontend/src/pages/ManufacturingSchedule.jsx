import { useCallback, useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import { Callout, DataTable, Loading, Panel, Status, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

export default function ManufacturingSchedule({ notify, onShowSaga, can }) {
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    api.get('/api/scheduling/board?limit=40').then((r) => setData(r.data));
  }, []);

  useEffect(load, [load]);

  const propose = async (patientKey) => {
    const { ok, data: payload } = await api.post(`/api/scheduling/propose/${patientKey}`);
    if (!ok) return notify({ tone: 'fail', title: 'Proposal refused', body: refusalReason(payload) });
    notify({
      tone: 'warn',
      title: 'Proposal created',
      body: `${payload.proposal.proposal_id} awaits Manufacturing planner approval. No capacity has been reserved.`,
    });
    load();
  };

  const approve = async (patientKey) => {
    const { ok, status, data: payload } = await api.post(`/api/scheduling/approve/${patientKey}`);
    if (!ok) {
      notify({
        tone: 'fail',
        title: status === 403 ? 'Approval refused' : 'Request failed',
        body: refusalReason(payload),
      });
      return;
    }
    const compensated = payload.saga.state === 'COMPENSATED';
    notify({
      tone: compensated ? 'warn' : 'pass',
      title: label(payload.outcome),
      body: compensated
        ? 'MES rejected the slot. Capacity was released, an owned exception was raised and alternates are proposed.'
        : 'Reservation confirmed across the scheduler and MES.',
    });
    onShowSaga(payload);
    load();
  };

  if (!data) return <Loading />;

  return (
    <>
      <Callout tone="info" title="Confirmation rule">{data.rule}</Callout>

      {data.pending_approvals.length > 0 && (
        <Panel
          title="Awaiting planner approval"
          note="A proposal reserves nothing. Approval runs the reservation workflow, which compensates automatically if MES rejects."
          flush
        >
          <DataTable
            columns={[
              { key: 'proposal_id', header: 'Proposal', render: (r) => <span className="mono">{r.proposal_id}</span> },
              { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono">{r.patient_key}</span> },
              { key: 'current', header: 'Current slot', render: (r) => <span className="mono">{r.current.slot_id} · {r.current.site_id}</span> },
              { key: 'status', header: 'Status', render: (r) => <Status value={r.status} /> },
              { key: 'idempotency_key', header: 'Idempotency key', render: (r) => <span className="mono subtle">{r.idempotency_key}</span> },
              {
                key: 'action',
                header: '',
                render: (r) => (can('reserve_slot_provisional') ? (
                  <button type="button" className="btn btn--primary btn--sm" onClick={() => approve(r.patient_key)}>
                    Approve as planner
                  </button>
                ) : (
                  <span className="subtle">Awaits {r.requires_approval}</span>
                )),
              },
            ]}
            rows={data.pending_approvals.map((p) => ({ ...p, id: p.proposal_id }))}
          />
        </Panel>
      )}

      <Panel title="Slot board" note="Scheduler state shown beside MES state. Rows where they disagree are highlighted." flush>
        <DataTable
          rowClassName={(row) => (row.conflict ? 'is-flagged' : '')}
          columns={[
            { key: 'slot_id', header: 'Slot', render: (r) => <span className="mono">{r.slot_id}</span> },
            { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono">{r.patient_key}</span> },
            { key: 'site_id', header: 'Site', render: (r) => <span className="mono">{r.site_id}</span> },
            { key: 'scheduled_start', header: 'Scheduled start', render: (r) => <span className="mono">{dateTime(r.scheduled_start)}</span> },
            { key: 'scheduler_state', header: 'Scheduler', render: (r) => <Status value={r.scheduler_state === 'CONFIRMED' ? 'PASS' : 'UNKNOWN'}>{label(r.scheduler_state)}</Status> },
            { key: 'mes_state', header: 'MES', render: (r) => <Status value={r.mes_state === 'CANCELLED' ? 'FAIL' : r.mes_state === 'READY' ? 'PASS' : 'UNKNOWN'}>{label(r.mes_state)}</Status> },
            { key: 'priority', header: 'Priority', align: 'right', render: (r) => <span className="mono">{r.priority}</span> },
            {
              key: 'shadow_priority',
              header: 'Offline sheet',
              render: (r) =>
                r.shadow_priority && r.shadow_priority !== r.priority ? (
                  <>
                    <Status value="CONFLICT">{r.shadow_priority}</Status>
                    {r.planner_note && <div className="subtle" style={{ marginTop: 4 }}>{r.planner_note}</div>}
                  </>
                ) : (
                  <span className="subtle">—</span>
                ),
            },
            {
              key: 'action',
              header: '',
              render: (r) => (can('draft_schedule') ? (
                <button type="button" className="btn btn--outline btn--sm" onClick={() => propose(r.patient_key)}>
                  Propose change
                </button>
              ) : (
                <span className="subtle">Manufacturing planner only</span>
              )),
            },
          ]}
          rows={data.slots.map((s) => ({ ...s, id: s.slot_id }))}
        />
      </Panel>
    </>
  );
}

export function SagaDetail({ payload }) {
  if (!payload) return null;
  const { saga, idempotency, dead_letter: deadLetter } = payload;

  return (
    <>
      <div className="row" style={{ marginBottom: 18 }}>
        <Status value={saga.state} />
        <Tag>Correlation {saga.correlation_id}</Tag>
        {saga.requires_approval && <Tag>Approval: {saga.requires_approval}</Tag>}
      </div>

      <Panel title="Retry safety" note="The legacy reservation service mints a new identifier on every retry, double-booking the scarcest asset in the network.">
        <DataTable
          columns={[
            { key: 'metric', header: 'Measure' },
            { key: 'value', header: 'Result', align: 'right' },
          ]}
          rows={[
            { id: 1, metric: 'Reservation attempts', value: <span className="mono">{idempotency.attempts}</span> },
            { id: 2, metric: 'Distinct reservations created', value: <strong style={{ color: 'var(--pass)' }}>{idempotency.distinct_reservations}</strong> },
            { id: 3, metric: 'Idempotent replays', value: <span className="mono">{idempotency.idempotent_replays}</span> },
          ]}
        />
      </Panel>

      <Panel title="Workflow steps" flush>
        <DataTable
          columns={[
            { key: 'name', header: 'Step', render: (r) => <span className="mono">{r.name}</span> },
            { key: 'state', header: 'Outcome', render: (r) => <Status value={r.state} /> },
            { key: 'attempts', header: 'Attempts', align: 'right' },
            { key: 'error', header: 'Detail', render: (r) => <span className="muted">{r.error || '—'}</span> },
          ]}
          rows={saga.steps.map((s, i) => ({ ...s, id: i }))}
        />
      </Panel>

      {saga.exception && (
        <Panel title="Exception raised">
          <DataTable
            columns={[{ key: 'k', header: 'Field' }, { key: 'v', header: 'Value' }]}
            rows={[
              { id: 1, k: 'Reference', v: <span className="mono">{saga.exception.exception_id}</span> },
              { id: 2, k: 'Owner', v: saga.exception.owner },
              { id: 3, k: 'Service level', v: `${saga.exception.sla_hours} hours` },
              { id: 4, k: 'Detail', v: saga.exception.detail },
            ]}
          />
        </Panel>
      )}

      {saga.alternatives?.length > 0 && (
        <Panel
          title="Proposed alternative sites"
          note="Advisory only. Nothing is rebooked automatically; a named planner approves or rejects."
          flush
        >
          <DataTable
            columns={[
              { key: 'name', header: 'Site', render: (r) => (<><div>{r.name}</div><div className="mono subtle">{r.site_id}</div></>) },
              { key: 'country', header: 'Country' },
              { key: 'qc_capacity_day', header: 'QC per day', align: 'right' },
              { key: 'headroom_pct', header: 'Headroom', align: 'right', render: (r) => <strong style={{ color: 'var(--pass)' }}>{r.headroom_pct}%</strong> },
              { key: 'trade_off', header: 'Trade-off', render: (r) => <span className="muted">{r.trade_off}</span> },
            ]}
            rows={saga.alternatives.map((a) => ({ ...a, id: a.site_id }))}
          />
        </Panel>
      )}

      <Panel title="Recovery queue">
        <p className="panel__note" style={{ margin: 0 }}>
          {(deadLetter || []).length} item(s) queued for manual recovery.
        </p>
      </Panel>
    </>
  );
}
