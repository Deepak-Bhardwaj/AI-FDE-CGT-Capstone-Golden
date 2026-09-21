import { useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import JourneyFlow, { day } from '../components/JourneyFlow';
import { Callout, DataTable, Loading, Panel, Redactable, SectionTitle, Status, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

const BLANK = {
  full_name: '', dob: '', center_id: '', product_code: '',
  referral_source: '', planned_enrolment: new Date().toISOString().slice(0, 10),
};

export default function PatientOnboarding({ notify }) {
  const [reference, setReference] = useState(null);
  const [registry, setRegistry] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [playToken, setPlayToken] = useState(0);

  const loadRegistry = () => api.get('/api/enrolment').then((r) => setRegistry(r.data));

  useEffect(() => {
    api.get('/api/enrolment/reference').then((r) => setReference(r.data));
    loadRegistry();
  }, []);

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    const { ok, data } = await api.post('/api/enrolment/register', form);
    setBusy(false);
    if (!ok) {
      setError(refusalReason(data));
      return;
    }
    setResult(data);
    setPlayToken((n) => n + 1);
    setForm(BLANK);
    loadRegistry();
    notify({
      tone: data.registration.duplicate_candidates.length ? 'warn' : 'pass',
      title: data.registration.registration_id,
      body: data.next_step,
    });
  };

  const adjudicate = async (registration, decision) => {
    const pending = (registry.approvals || []).find(
      (a) => a.subject === registration.registration_id,
    );
    if (pending && !pending.can_countersign) {
      notify({ tone: 'warn', title: 'Awaiting a second adjudicator', body: pending.blocked_reason });
      return;
    }
    const signature = window.prompt('Type your name to sign this adjudication:');
    if (!signature || signature.trim().length < 4) return;

    if (pending) {
      const { ok, data } = await api.post(
        `/api/enrolment/${registration.registration_id}/decide/countersign`,
        { approval_id: pending.approval_id, e_signature: signature },
      );
      notify(ok
        ? { tone: 'pass', title: label(data.outcome), body: `${registration.registration_id} adjudicated on two signatures.` }
        : { tone: 'fail', title: 'Refused', body: refusalReason(data) });
      if (ok) loadRegistry();
      return;
    }

    const reason = window.prompt(`Reason for ${decision.toLowerCase()} (10 characters or more):`);
    if (!reason) return;
    const { ok, data } = await api.post(
      `/api/enrolment/${registration.registration_id}/decide`,
      { decision, reason, e_signature: signature },
    );
    notify(ok
      ? {
        tone: 'warn',
        title: 'Awaiting a second adjudicator',
        body: 'Your signature is recorded. The registration has not moved until a different '
          + 'adjudicator countersigns.',
      }
      : { tone: 'fail', title: 'Refused', body: refusalReason(data) });
    if (ok) loadRegistry();
  };

  if (!reference || !registry) return <Loading />;

  return (
    <>
      <Callout tone="info" title="What registering here does, and does not do">
        This control tower is not a system of record. A registration creates a provisional record
        with its own identifier (PR-00001), so it can never be mistaken for a CRM or clinical
        enrolment. If the details match someone already in the estate, nothing is created: the
        submission is held for the identity adjudicator, because a duplicate patient record is a
        wrong-patient risk.
      </Callout>

      {registry.may_register ? (
        <Panel title="Register a new patient" note="Every field is checked against the reference data. The medical record number is issued here in a provisional 9xxxxx block, so it can never collide with one a source system issued.">
          {error && <Callout tone="fail" title="Not accepted">{error}</Callout>}
          <form className="formgrid" onSubmit={submit}>
            <label className="formgrid__field">
              <span>Full name</span>
              <input className="field" value={form.full_name} onChange={set('full_name')} required />
            </label>
            <label className="formgrid__field">
              <span>Date of birth</span>
              <input className="field" type="date" value={form.dob} onChange={set('dob')} required />
            </label>
            <label className="formgrid__field">
              <span>Medical record number</span>
              <input className="field" value="Issued automatically on registration" readOnly disabled />
            </label>
            <label className="formgrid__field">
              <span>Treatment centre</span>
              <select className="field" value={form.center_id} onChange={set('center_id')} required>
                <option value="">Select a centre</option>
                {reference.centres.map((c) => (
                  <option key={c.center_id} value={c.center_id}>
                    {c.center_id} — {c.name} ({c.country})
                  </option>
                ))}
              </select>
            </label>
            <label className="formgrid__field">
              <span>Product</span>
              <select className="field" value={form.product_code} onChange={set('product_code')} required>
                <option value="">Select a product</option>
                {reference.products.map((p) => (
                  <option key={p.product_code} value={p.product_code}>
                    {p.product_code} — {p.name} · {p.indication}
                  </option>
                ))}
              </select>
            </label>
            <label className="formgrid__field">
              <span>Referral source</span>
              <input className="field" placeholder="Referring clinician or centre" value={form.referral_source} onChange={set('referral_source')} required />
            </label>
            <label className="formgrid__field">
              <span>Planned enrolment date</span>
              <input className="field" type="date" value={form.planned_enrolment} onChange={set('planned_enrolment')} required />
            </label>
            <div className="formgrid__actions">
              <button type="submit" className="btn btn--primary" disabled={busy}>
                {busy ? 'Checking…' : 'Register and project the journey'}
              </button>
            </div>
          </form>
        </Panel>
      ) : (
        <Panel title="Register a new patient">
          <p className="panel__note" style={{ margin: 0 }}>
            Registration belongs to the Operations coordinator. This page is read-only for your role.
          </p>
        </Panel>
      )}

      {result && (
        <>
          <Callout
            tone={result.registration.duplicate_candidates.length ? 'conflict' : 'pass'}
            title={`${result.registration.registration_id} — ${label(result.registration.status)}`}
          >
            <div className="row" style={{ marginBottom: 8 }}>
              <Tag>Issued medical record number <Redactable value={result.registration.mrn} /></Tag>
            </div>
            {result.next_step}
            {result.registration.duplicate_candidates.length > 0 && (
              <ul className="steps" style={{ marginTop: 8 }}>
                {result.registration.duplicate_candidates.map((c) => (
                  <li key={c.patient_key}>
                    <span className="mono">{c.patient_key}</span> — {c.matched_on.join(', ')}
                  </li>
                ))}
              </ul>
            )}
          </Callout>

          <SectionTitle>The journey this patient can expect</SectionTitle>
          <Panel note="Rolled forward from the planned enrolment date using this estate's own history. A planning aid, not a schedule.">
            <div className="row" style={{ marginBottom: 14 }}>
              <Tag>Planned enrolment {day(result.projection.start)}</Tag>
              <Tag>Most likely release {day(result.projection.ready_window.expected)}</Tag>
              <Tag>{result.projection.expected_total_days} days vein-to-release</Tag>
              <button type="button" className="btn btn--outline btn--sm" onClick={() => setPlayToken((n) => n + 1)}>
                ▶ Replay
              </button>
            </div>
            <JourneyFlow steps={result.projection.steps} playToken={playToken} />
          </Panel>
        </>
      )}

      <SectionTitle>Registrations</SectionTitle>
      <Panel note="Provisional until reconciled with the clinical system of record. Held registrations are released only by the identity adjudicator." flush>
        <DataTable
          columns={[
            { key: 'registration_id', header: 'Reference', render: (r) => <span className="mono">{r.registration_id}</span> },
            { key: 'full_name', header: 'Patient', render: (r) => <Redactable value={r.full_name} /> },
            { key: 'mrn', header: 'Record number', render: (r) => <span className="mono"><Redactable value={r.mrn} /></span> },
            { key: 'center_id', header: 'Centre', render: (r) => <span className="mono">{r.center_id}</span> },
            { key: 'planned_enrolment', header: 'Planned enrolment', render: (r) => <span className="mono">{r.planned_enrolment}</span> },
            { key: 'status', header: 'Status', render: (r) => <Status value={r.status} /> },
            {
              key: 'duplicate_candidates', header: 'Possible existing record',
              render: (r) => (r.duplicate_candidates.length
                ? <span className="mono">{r.duplicate_candidates.map((c) => c.patient_key).join(', ')}</span>
                : <span className="subtle">None</span>),
            },
            { key: 'registered_by', header: 'Registered by', render: (r) => <span className="subtle">{r.registered_by} · {dateTime(r.registered_at)}</span> },
            {
              key: 'actions', header: '',
              render: (r) => (r.status === 'NEEDS_ADJUDICATION' && registry.may_adjudicate ? (
                <div className="row" style={{ flexWrap: 'nowrap' }}>
                  <button type="button" className="btn btn--primary btn--sm" onClick={() => adjudicate(r, 'CONFIRMED')}>Distinct patient</button>
                  <button type="button" className="btn btn--outline btn--sm" onClick={() => adjudicate(r, 'REJECTED')}>Same patient</button>
                </div>
              ) : r.status === 'NEEDS_ADJUDICATION' ? (
                <span className="subtle">Awaits Identity adjudicator</span>
              ) : (
                <span className="subtle">{r.decided_by ? `${label(r.status)} by ${r.decided_by}` : '—'}</span>
              )),
            },
          ]}
          rows={registry.registrations.map((r) => ({ ...r, id: r.registration_id }))}
          empty="No one has been registered here yet."
        />
      </Panel>
    </>
  );
}
