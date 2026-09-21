import { useState } from 'react';
import { api, refusalReason } from '../api/client';
import { Callout, Loading, Panel, SectionTitle, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

/** Best available human-readable summary of whatever an operation returned. */
function outcomeText(data) {
  return (
    data?.decision?.rationale
    || data?.reason
    || data?.saga?.outcome
    || (data?.outcome ? label(data.outcome) : null)
    || 'The request was recorded.'
  );
}

export default function StageAction({ plan, notify, onRunAgent, onOpenReadiness, onRefresh }) {
  const [busy, setBusy] = useState(null);
  const [kind, setKind] = useState('');
  const [justification, setJustification] = useState('');
  const [signature, setSignature] = useState('');

  if (!plan) return <Loading />;

  const choice = plan.decisions.find((d) => d.id === kind);
  const myOperations = plan.operations.filter((op) => op.permitted);
  const otherOperations = plan.operations.filter((op) => !op.permitted);
  const myDecisions = plan.decisions.filter((d) => d.permitted);

  const run = async (op) => {
    setBusy(op.id);
    const { ok, data } = await api.post(op.path);
    setBusy(null);
    if (!ok) {
      notify({ tone: 'fail', title: 'Refused', body: refusalReason(data) });
      return;
    }
    notify({
      tone: data.outcome === 'EXECUTED' ? 'pass' : 'warn',
      title: op.label,
      body: outcomeText(data),
    });
  };

  const withdraw = async () => {
    setBusy('withdraw');
    const { ok, data } = await api.post(`/api/attestations/${plan.attestation.attestation_id}/withdraw`);
    setBusy(null);
    if (!ok) {
      notify({ tone: 'fail', title: 'Refused', body: refusalReason(data) });
      return;
    }
    notify({
      tone: 'warn',
      title: 'Attestation withdrawn',
      body: 'The gate has returned to what the source systems say.',
    });
    onRefresh?.();
  };

  const record = async (event) => {
    event.preventDefault();
    setBusy('decision');
    const { ok, data } = await api.post(
      `/api/workflow/${plan.patient_key}/actions/${plan.stage_id}/decide`,
      { decision: kind, justification, e_signature: signature },
    );
    setBusy(null);
    if (!ok) {
      notify({ tone: 'fail', title: 'Not recorded', body: refusalReason(data) });
      return;
    }
    notify({
      tone: 'pass',
      title: 'Decision recorded',
      body: `${data.decision.decision_id} — signed by ${data.decision.approved_by}.`,
    });
    setKind('');
    setJustification('');
    setSignature('');
    onRefresh?.();
  };

  return (
    <>
      <Callout tone={plan.status === 'CONFLICT' ? 'conflict' : 'fail'} title={plan.action}>
        {plan.detail}
      </Callout>

      {plan.attestation && (
        <Callout tone="warn" title="Cleared on a signed attestation, not on source evidence">
          <div>
            {plan.attestation.by} ({plan.attestation.authority}) attested on{' '}
            {dateTime(plan.attestation.attested_at)}: {plan.attestation.justification}
          </div>
          <div className="subtle" style={{ marginTop: 6 }}>
            Signed {plan.attestation.e_signature} · {plan.attestation.attestation_id}. The gate
            will revert if this is withdrawn or the source data contradicts it.
          </div>
          {plan.may_withdraw && (
            <button
              type="button"
              className="btn btn--outline btn--sm"
              style={{ marginTop: 10 }}
              disabled={busy === 'withdraw'}
              onClick={withdraw}
            >
              {busy === 'withdraw' ? 'Withdrawing…' : 'Withdraw this attestation'}
            </button>
          )}
        </Callout>
      )}

      {plan.handling && !plan.attestation && (
        <Callout tone="info" title={`${label(plan.handling.state)} — ${plan.handling.by}`}>
          <div>{plan.handling.note}</div>
          <div className="subtle" style={{ marginTop: 6 }}>
            {dateTime(plan.handling.at)}. This records who owns the stage. The stage is still
            blocked: it clears when the authority confirms the correction under signature, or when
            the source systems themselves report the corrected evidence.
          </div>
        </Callout>
      )}

      <SectionTitle>Who may do this</SectionTitle>
      <Panel>
        <div className="row">
          <Tag>Authority: {plan.authority}</Tag>
          <Tag>Stage owner: {plan.owner}</Tag>
          {plan.gate_ids.map((g) => <Tag key={g}>{g}</Tag>)}
        </div>
        <p className="panel__note" style={{ marginTop: 10, marginBottom: 0 }}>
          {plan.you_hold_the_authority
            ? `You hold this authority as ${label(plan.your_role)}, so the sign-off below is yours to make.`
            : plan.authorized_role
              ? `This decision belongs to the ${plan.authorized_role_label}. You are signed in as ${label(plan.your_role)}, so you can see it and hand it on, but not sign it off.`
              : `No role in this control tower carries the ${plan.authority} authority — the work is done in the source system and read back here.`}
        </p>
      </Panel>

      {plan.steps.length > 0 && (
        <>
          <SectionTitle>What has to happen</SectionTitle>
          <Panel note="These steps happen in the source systems. This control tower reads them; it never writes to them.">
            <ol className="steps">
              {plan.steps.map((step) => <li key={step}>{step}</li>)}
            </ol>
          </Panel>
        </>
      )}

      <SectionTitle>What you can do here</SectionTitle>
      <Panel note="Every operation below is a proposal. It is still refused, with a recorded reason, if the signature or the open gates do not allow it.">
        {myOperations.length === 0 ? (
          <p className="panel__note" style={{ margin: 0 }}>
            There is no system operation here for your role. The evidence has to change at source.
          </p>
        ) : (
          <div className="stack">
            {myOperations.map((op) => (
              <div key={op.id} className="op">
                <div className="op__text">
                  <div className="op__label">{op.label}</div>
                  <div className="op__effect">{op.effect}</div>
                </div>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={busy === op.id}
                  onClick={() => run(op)}
                >
                  {busy === op.id ? 'Working…' : 'Run'}
                </button>
              </div>
            ))}
          </div>
        )}
        {otherOperations.length > 0 && (
          <p className="panel__note" style={{ marginTop: 12, marginBottom: 0 }}>
            Held by another duty: {otherOperations.map((op) => `${op.label} (${op.roles.map(label).join(', ')})`).join('; ')}.
          </p>
        )}
        <div className="row" style={{ marginTop: 14 }}>
          <button type="button" className="btn btn--ghost" onClick={() => onRunAgent('AG-EXPLAIN', plan.patient_key)}>
            Explain this blockage
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => onOpenReadiness(plan.patient_key)}>
            Open readiness detail
          </button>
        </div>
      </Panel>

      {plan.evidence_refs?.length > 0 && (
        <>
          <SectionTitle>Evidence behind this stage</SectionTitle>
          <Panel>
            <div className="row">
              {plan.evidence_refs.map((ref) => <Tag key={ref}>{ref}</Tag>)}
            </div>
          </Panel>
        </>
      )}

      <SectionTitle>Record what you decided</SectionTitle>
      <Panel note="The work happens in the source systems. What is captured here is who decided what, why, and when — it never changes a gate or a source record.">
        {myDecisions.length === 0 ? (
          <p className="panel__note" style={{ margin: 0 }}>
            Your role is read-only for this stage. Nothing here is yours to record.
          </p>
        ) : (
          <form onSubmit={record} className="stack">
            <div className="stack" style={{ gap: 6 }}>
              {myDecisions.map((option) => (
                <label key={option.id} className="choice">
                  <input
                    type="radio"
                    name="stage-decision"
                    value={option.id}
                    checked={kind === option.id}
                    onChange={() => setKind(option.id)}
                  />
                  <span>
                    <span className="choice__label">
                      {option.label}
                      {option.clears_gate && <span className="choice__flag">clears the gate</span>}
                    </span>
                    <span className="choice__help">{option.help}</span>
                  </span>
                </label>
              ))}
            </div>

            <textarea
              className="field"
              rows={3}
              placeholder="Why, and what you did. At least 10 characters — this goes on the record."
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              aria-label="Justification"
            />

            {choice?.requires_signature && (
              <input
                className="field"
                placeholder="Electronic signature — type your full name"
                value={signature}
                onChange={(e) => setSignature(e.target.value)}
                aria-label="Electronic signature"
              />
            )}

            <div className="row">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={!choice || justification.trim().length < 10
                  || (choice?.requires_signature && !signature.trim()) || busy === 'decision'}
              >
                {busy === 'decision' ? 'Recording…' : 'Record this decision'}
              </button>
              <span className="subtle">Signed as {label(plan.your_role)}.</span>
            </div>
          </form>
        )}
      </Panel>

      {plan.recorded?.length > 0 && (
        <>
          <SectionTitle>Already on the record</SectionTitle>
          <Panel flush>
            <div className="stack" style={{ padding: '14px 18px' }}>
              {plan.recorded.map((entry) => (
                <div key={entry.decision_id} className="op">
                  <div className="op__text">
                    <div className="op__label">{label(entry.outcome)}</div>
                    <div className="op__effect">{entry.rationale}</div>
                    <div className="op__blocked" style={{ color: 'var(--text-subtle)' }}>
                      {entry.approved_by} · {dateTime(entry.decided_at)}
                      {entry.e_signature && ' · electronically signed'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
