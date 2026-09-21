import { useCallback, useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import { Callout, DataTable, Loading, Panel, SectionTitle, Status, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

const STATE_TONE = {
  released: 'pass',
  rejected: 'fail',
  on_hold: 'fail',
  pending_disposition: 'warn',
};

export default function ReviewerPacket({ lotId, notify, onRefresh }) {
  const [packet, setPacket] = useState(null);
  const [error, setError] = useState('');
  const [signature, setSignature] = useState('');
  const [justification, setJustification] = useState('');
  const [rationale, setRationale] = useState('');
  const [withdrawal, setWithdrawal] = useState('');

  const load = useCallback(async () => {
    const { ok, data } = await api.get(`/api/lots/${lotId}/reviewer-packet`);
    if (!ok) { setError(refusalReason(data)); return; }
    setPacket(data);
  }, [lotId]);

  useEffect(() => { load(); }, [load]);

  if (error) return <Callout tone="fail">{error}</Callout>;
  if (!packet) return <Loading />;

  const { evidence, verdict, provenance, disposition } = packet;
  const awaiting = disposition.awaiting_countersignature;
  const standing = disposition.standing_rejection;
  const withdrawn = (disposition.rejections || []).filter((r) => !r.standing);
  const mine = disposition.yours_to_withdraw || [];

  const sign = async () => {
    const { ok, data } = await api.post(`/api/release/${evidence.identifiers.patient_ref}/approve`,
      { e_signature: signature, justification });
    if (!ok) { notify({ tone: 'fail', title: 'Release refused', body: refusalReason(data) }); return; }
    setSignature('');
    notify({
      tone: 'warn',
      title: 'Awaiting a second approver',
      body: 'Your signature is recorded. Nothing has been released.',
    });
    load();
  };

  const countersign = async () => {
    const { ok, data } = await api.post(
      `/api/release/${evidence.identifiers.patient_ref}/countersign`,
      { approval_id: awaiting.approval_id, e_signature: signature },
    );
    if (!ok) { notify({ tone: 'fail', title: 'Countersignature refused', body: refusalReason(data) }); return; }
    setSignature('');
    notify({
      tone: 'pass',
      title: 'Released',
      body: `Executed on two signatures: ${data.decision.approved_by} and ${data.decision.countersigned_by}.`,
    });
    load();
    onRefresh?.();
  };

  const reject = async () => {
    const { ok, data } = await api.post(`/api/release/${evidence.identifiers.patient_ref}/reject`,
      { rationale });
    if (!ok) { notify({ tone: 'fail', title: 'Rejection refused', body: refusalReason(data) }); return; }
    setRationale('');
    notify({
      tone: 'warn',
      title: `Rejection ${data.rejection.rejection_id} recorded`,
      body: 'This lot is blocked until you withdraw it. Nobody else can.',
    });
    load();
    onRefresh?.();
  };

  const withdraw = async (rejectionId) => {
    const { ok, data } = await api.post(`/api/rejections/${rejectionId}/withdraw`,
      { reason: withdrawal });
    if (!ok) { notify({ tone: 'fail', title: 'Withdrawal refused', body: refusalReason(data) }); return; }
    setWithdrawal('');
    notify({
      tone: 'pass',
      title: `${rejectionId} withdrawn`,
      body: 'The rejection stays in the record with your reason for withdrawing it.',
    });
    load();
    onRefresh?.();
  };

  return (
    <>
      <div className="packet__head">
        <div>
          <div className="packet__lot">{packet.lot_id || evidence.identifiers.patient_ref}</div>
          <div className="packet__sub">
            Assembled {dateTime(packet.assembled_at)} · {packet.packet_version}
          </div>
        </div>
        <Status value={verdict.recommendation === 'BLOCK_RELEASE' ? 'FAIL' : 'PASS'} />
      </div>

      <Callout tone={STATE_TONE[evidence.state.canonical_state] || 'warn'}>
        <strong>{label(evidence.state.canonical_state)}</strong> — {evidence.state.canonical_state_reason}
      </Callout>

      <div className="packet">
        <section className="packet__col">
          <SectionTitle>What is true</SectionTitle>
          <Panel note="Assembled by query from the operational records. Identity is looked up by identifier, never matched by similarity.">
            <dl className="packet__ids">
              {Object.entries(evidence.identifiers).map(([key, value]) => (
                <div key={key}>
                  <dt>{label(key)}</dt>
                  <dd>{value === true ? 'Yes' : value === false ? 'No' : (value || '—')}</dd>
                </div>
              ))}
            </dl>
            <div className="packet__states">
              {['mes_state', 'erp_state', 'qms_state'].map((key) => (
                <span key={key} className="packet__state">
                  <em>{label(key)}</em> {evidence.state[key] || '—'}
                </span>
              ))}
            </div>
          </Panel>

          <SectionTitle>Quality control</SectionTitle>
          <DataTable
            columns={[
              { key: 'assay', header: 'Assay', render: (r) => label(r.assay) },
              { key: 'disposition', header: 'Result', render: (r) => <Status value={r.disposition} /> },
              { key: 'value', header: 'Value', render: (r) => (r.value ? `${r.value} ${r.unit || ''}` : '—') },
              { key: 'event_id', header: 'Record', render: (r) => r.event_id || <span className="subtle">not reported</span> },
            ]}
            rows={evidence.qc.map((q) => ({ id: q.assay, ...q }))}
          />

          {evidence.conflicts.length > 0 && (
            <>
              <SectionTitle>Where the systems disagree</SectionTitle>
              {evidence.conflicts.map((c) => (
                <Panel key={`${c.field}-${c.left.source}`}>
                  <div className="packet__conflict">
                    <span><em>{c.left.source}</em> {JSON.stringify(c.left.value)}</span>
                    <span className="packet__versus">vs</span>
                    <span><em>{c.right.source}</em> {JSON.stringify(c.right.value)}</span>
                  </div>
                  <div className="packet__note">{c.note}</div>
                </Panel>
              ))}
            </>
          )}

          {evidence.holds.length > 0 && (
            <>
              <SectionTitle>Holds</SectionTitle>
              {evidence.holds.map((h, i) => (
                <div key={`${h.code}-${i}`} className="packet__hold">
                  <Tag>{h.code}</Tag> <span className="subtle">{h.source}</span>
                  <div>{h.detail}</div>
                </div>
              ))}
            </>
          )}
        </section>

        <section className="packet__col">
          <SectionTitle>The rule that fired</SectionTitle>
          <Panel note="Every verdict below names the rule that produced it, its version, and the system whose word decides it.">
            {verdict.gates.map((g) => (
              <div key={g.gate_id} className={`packet__gate packet__gate--${g.status}`}>
                <div className="packet__gate-head">
                  <span className="gate__id">{g.gate_id}</span>
                  <span className="gate__name">{g.name}</span>
                  <Status value={g.status} />
                </div>
                <div className="packet__gate-reason">{g.reason}</div>
                <div className="gate__rule">
                  <span className="gate__rule-id">{g.fired}</span>
                  <span className="gate__rule-meta">
                    {g.rule_id} v{g.rule_version} · {g.source_system}
                  </span>
                  <div className="gate__rule-text">{g.rule_statement}</div>
                </div>
                {g.advisory?.map((note) => (
                  <div key={note} className="gate__advisory">⚠ {note}</div>
                ))}
              </div>
            ))}
          </Panel>
        </section>

        <section className="packet__col">
          <SectionTitle>Decision</SectionTitle>

          {standing && (
            <Panel note={disposition.rejection_note}>
              <Callout tone="fail" title={`${standing.rejection_id} — rejected by Quality`}>
                <div className="packet__rationale">“{standing.rationale}”</div>
                <div className="packet__note">
                  {standing.by} ({standing.authority}) · {dateTime(standing.rejected_at)}
                </div>
              </Callout>
              {mine.includes(standing.rejection_id) ? (
                <div className="row">
                  <input
                    className="field"
                    style={{ maxWidth: 340 }}
                    value={withdrawal}
                    placeholder="What changed since you rejected it"
                    onChange={(e) => setWithdrawal(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn--outline"
                    disabled={withdrawal.trim().length < 20}
                    onClick={() => withdraw(standing.rejection_id)}
                  >
                    Withdraw my rejection
                  </button>
                </div>
              ) : (
                <p className="panel__note" style={{ marginBottom: 0 }}>
                  Only {standing.by} can withdraw this. If you disagree, record your own view —
                  you cannot remove a colleague’s decision.
                </p>
              )}
            </Panel>
          )}

          <Panel note={disposition.note}>
            {verdict.blocking_reasons.length > 0 ? (
              <>
                <Callout tone="fail" title={`${verdict.blocking_reasons.length} reason(s) prevent release`}>
                  <ul className="packet__blockers">
                    {verdict.blocking_reasons.map((r, i) => (
                      <li key={r}>
                        {r}
                        {verdict.rules_fired[i] && (
                          <span className="packet__firedby"> — {verdict.rules_fired[i]}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </Callout>
                <p className="panel__note" style={{ marginBottom: 0 }}>
                  Nothing can be signed while these stand. Resolving them at source, or
                  recording an attestation, is how they clear — and neither clears the QA
                  release gate itself.
                </p>
              </>
            ) : !disposition.may_release ? (
              <Callout tone="warn">{disposition.why_not}</Callout>
            ) : awaiting ? (
              <>
                <Callout tone="warn" title="Awaiting a second approver">
                  {awaiting.first_by} signed at {dateTime(awaiting.first_at)}. Nothing has been
                  released. This approval lapses at {dateTime(awaiting.expires_at)}.
                </Callout>
                {disposition.you_are_the_first_approver ? (
                  <p className="panel__note" style={{ marginBottom: 0 }}>
                    You requested this approval, so a different qualified person must
                    countersign it.
                  </p>
                ) : (
                  <div className="row">
                    <input
                      className="field"
                      style={{ maxWidth: 280 }}
                      value={signature}
                      placeholder="Type your name to countersign"
                      onChange={(e) => setSignature(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={signature.trim().length < 4}
                      onClick={countersign}
                    >
                      Countersign and release
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="row">
                <input
                  className="field"
                  style={{ maxWidth: 240 }}
                  value={signature}
                  placeholder="Type your name to sign"
                  onChange={(e) => setSignature(e.target.value)}
                />
                <input
                  className="field"
                  style={{ maxWidth: 300 }}
                  value={justification}
                  placeholder="Why this lot is releasable"
                  onChange={(e) => setJustification(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn--outline"
                  disabled={signature.trim().length < 4}
                  onClick={sign}
                >
                  Sign as first approver
                </button>
              </div>
            )}
          </Panel>

          {disposition.may_reject && !standing && (
            <>
              <SectionTitle>Reject this lot</SectionTitle>
              <Panel note="A rejection blocks release immediately and stays on the record. Your words are what the next reviewer reads, so a lot rejected on judgement is distinguishable from one merely waiting on evidence.">
                <textarea
                  className="field"
                  rows={3}
                  value={rationale}
                  placeholder="Why you are rejecting this lot"
                  onChange={(e) => setRationale(e.target.value)}
                />
                <div className="row">
                  <button
                    type="button"
                    className="btn btn--danger"
                    disabled={rationale.trim().length < 20}
                    onClick={reject}
                  >
                    Record rejection
                  </button>
                  <span className="subtle">
                    {rationale.trim().length < 20
                      ? `${20 - rationale.trim().length} more character(s) of reasoning required`
                      : 'Only you will be able to withdraw this'}
                  </span>
                </div>
              </Panel>
            </>
          )}

          {withdrawn.length > 0 && (
            <>
              <SectionTitle>Withdrawn rejections</SectionTitle>
              <Panel note="Kept deliberately. A reviewer who changed their mind, and why, is evidence.">
                {withdrawn.map((r) => (
                  <div key={r.rejection_id} className="packet__hold">
                    <Tag>{r.rejection_id}</Tag>{' '}
                    <span className="subtle">{r.by} · {dateTime(r.rejected_at)}</span>
                    <div className="packet__rationale">“{r.rationale}”</div>
                    <div className="packet__note">
                      Withdrawn {dateTime(r.withdrawn_at)}: {r.withdrawal_reason}
                    </div>
                  </div>
                ))}
              </Panel>
            </>
          )}

          <SectionTitle>Provenance</SectionTitle>
          <Panel note={provenance.assembled_from}>
            <dl className="packet__ids">
              <div><dt>Policy</dt><dd>{provenance.policy_version}</dd></div>
              <div><dt>Specification</dt><dd>{provenance.spec_version}</dd></div>
              <div><dt>SOP</dt><dd>{provenance.sop.sop_id} {provenance.sop.sop_version}</dd></div>
              <div><dt>Rule set</dt><dd>{provenance.rule_version}</dd></div>
              <div><dt>Model</dt><dd>{provenance.model.name}</dd></div>
            </dl>
            <div className="packet__note">{provenance.mechanism}</div>
          </Panel>
        </section>
      </div>
    </>
  );
}
