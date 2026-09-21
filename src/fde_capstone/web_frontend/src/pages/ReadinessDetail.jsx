import { useCallback, useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import {
  Callout, DataTable, DefinitionList, Loading, Panel, Redactable, SectionTitle, Status, Tag,
} from '../components/ui';
import { dateTime, label, percent } from '../lib/format';

const FACT_LABELS = {
  'identity.dob': 'Date of birth',
  'identity.mrn': 'Medical record number',
  'identity.center_id': 'Treatment centre',
  'identity.mrn_unique': 'Medical record number is unique',
  'consent.status': 'Consent status',
  'consent.version': 'Consent version',
  'authorization.status': 'Payer authorization',
  'center.qualified': 'Centre fully qualified',
  'collection.quality': 'Collection quality flag',
  'collection.coi': 'Chain-of-identity reference',
  'custody.intact': 'Custody intact',
  'slot.confirmed': 'Slot confirmed',
  'mfg.state': 'Manufacturing state',
  'qc.complete': 'QC evidence complete',
  'deviations.open': 'Open deviations',
  'product.released': 'Released by Quality',
  'batch.id': 'Batch',
  'timeline.events': 'Recorded events',
};

const HIDDEN_FACTS = new Set(['custody.excursion_profiles', 'qc.summary']);

export default function ReadinessDetail({ detail, notify, onRunAgent, onRefresh, onOpenPacket, can }) {
  const [approval, setApproval] = useState(null);
  const [signature, setSignature] = useState('');
  const [justification, setJustification] = useState('');
  const patientKey = detail?.journey?.patient_key;

  const loadApprovals = useCallback(async () => {
    if (!patientKey || !can('release_product')) return;
    const { ok, data } = await api.get('/api/approvals?action=release_product');
    if (!ok) return;
    setApproval((data.approvals || []).find((a) => a.subject === patientKey) || null);
  }, [patientKey, can]);

  useEffect(() => { loadApprovals(); }, [loadApprovals]);

  if (!detail) return <Loading />;

  const { journey, readiness, legacy, access } = detail;
  const facts = Object.entries(journey.facts || {}).filter(([key]) => !HIDDEN_FACTS.has(key));

  const signFirst = async () => {
    const { ok, data } = await api.post(`/api/release/${journey.patient_key}/approve`,
      { e_signature: signature, justification });
    if (!ok) {
      notify({ tone: 'fail', title: 'Release refused', body: refusalReason(data) });
      return;
    }
    setSignature('');
    notify({
      tone: 'warn',
      title: 'Awaiting a second approver',
      body: 'Your signature is recorded. Nothing has been released. A different qualified person '
        + 'must countersign before this executes.',
    });
    loadApprovals();
  };

  const countersign = async () => {
    const { ok, data } = await api.post(`/api/release/${journey.patient_key}/countersign`,
      { approval_id: approval.approval_id, e_signature: signature });
    if (!ok) {
      notify({ tone: 'fail', title: 'Countersignature refused', body: refusalReason(data) });
      return;
    }
    setSignature('');
    notify({
      tone: 'pass',
      title: 'Released',
      body: `Executed on two signatures: ${data.decision.approved_by} and ${data.decision.countersigned_by}.`,
    });
    loadApprovals();
    onRefresh?.();
  };

  const proposeLink = async () => {
    const { ok, data } = await api.post(`/api/identity/${journey.patient_key}/merge`,
      { e_signature: 'proposed' });
    notify(
      ok
        ? { tone: 'warn', title: 'Merge candidate', body: data.decision.rationale }
        : { tone: 'fail', title: 'Merge refused', body: refusalReason(data) },
    );
  };

  return (
    <>
      <div className="gate-strip">
        {readiness.gates.map((gate) => (
          <span key={gate.gate_id} className={gate.status} title={`${gate.gate_id} — ${label(gate.status)}`} />
        ))}
      </div>

      <Callout tone={readiness.readiness === 'CONFLICTED' ? 'conflict' : readiness.readiness === 'READY' ? 'pass' : 'warn'}>
        {readiness.recommendation}
      </Callout>

      {legacy?.legacy_product_ready === true && (
        <Callout tone="fail" title="The legacy rule disagrees">
          Legacy <code>product_ready({legacy.batch_id})</code> returns <strong>true</strong> — MES{' '}
          {label(legacy.mes_status)}, ERP {label(legacy.erp_status)}, Quality {label(legacy.qms_release_status)}.
          <div style={{ marginTop: 6 }}>{legacy.note}</div>
        </Callout>
      )}

      <SectionTitle>Readiness gates</SectionTitle>
      <div className="gate-grid">
        {readiness.gates.map((gate) => (
          <div key={gate.gate_id} className={`gate gate--${gate.status}`}>
            <div className="gate__head">
              <span className="gate__id">{gate.gate_id}</span>
              <span className="gate__name">{gate.name}</span>
              <Status value={gate.status} />
            </div>
            <div className="gate__reason">{gate.reason}</div>
            {gate.rule_id && (
              <div className="gate__rule" title={gate.rule_statement}>
                <span className="gate__rule-id">{gate.fired}</span>
                <span className="gate__rule-meta">
                  {gate.rule_id} v{gate.rule_version} · {gate.source_system}
                </span>
                <div className="gate__rule-text">{gate.rule_statement}</div>
              </div>
            )}
            <div className="gate__meta">
              Authority: {gate.authority}
              {gate.sop_ref && ` · ${gate.sop_ref}`}
            </div>
            {gate.advisory?.map((note) => (
              <div key={note} className="gate__advisory">⚠ {note}</div>
            ))}
          </div>
        ))}
      </div>

      {journey.blocking_reasons?.length > 0 && (
        <>
          <SectionTitle>Blocking reasons</SectionTitle>
          {journey.blocking_reasons.map((reason) => (
            <Callout key={reason} tone="fail">{reason}</Callout>
          ))}
        </>
      )}

      {journey.uncertainties?.length > 0 && (
        <>
          <SectionTitle>Uncertainty — recorded, not repaired</SectionTitle>
          {journey.uncertainties.map((note) => (
            <Callout key={note} tone="warn">{note}</Callout>
          ))}
        </>
      )}

      {journey.shadow_signals?.length > 0 && (
        <>
          <SectionTitle>Decisions taken outside the system</SectionTitle>
          {journey.shadow_signals.map((note) => (
            <Callout key={note} tone="conflict">{note}</Callout>
          ))}
        </>
      )}

      <SectionTitle>Reconciled facts</SectionTitle>
      <Panel flush>
        <DataTable
          columns={[
            { key: 'name', header: 'Fact', render: (r) => FACT_LABELS[r.name] || label(r.name) },
            {
              key: 'value', header: 'Value',
              render: (r) => {
                if (r.fact === '[redacted]') return <Redactable value="[redacted]" />;
                const value = r.fact.value;
                if (value === null || value === undefined) return <span className="subtle">Not established</span>;
                if (typeof value === 'boolean') return <Status value={value ? 'PASS' : 'FAIL'}>{value ? 'Yes' : 'No'}</Status>;
                if (Array.isArray(value)) return value.length ? <span className="mono">{value.join(', ')}</span> : <span className="subtle">None</span>;
                if (typeof value === 'object') return <span className="mono">{JSON.stringify(value)}</span>;
                return <span className="mono">{String(value)}</span>;
              },
            },
            {
              key: 'resolution', header: 'Resolution',
              render: (r) => (r.fact === '[redacted]' ? '—' : <Status value={r.fact.resolution} />),
            },
            {
              key: 'note', header: 'Note',
              render: (r) => (r.fact !== '[redacted]' && r.fact.note ? <span className="subtle">{r.fact.note}</span> : '—'),
            },
          ]}
          rows={facts.map(([name, fact]) => ({ id: name, name, fact }))}
        />
      </Panel>

      <SectionTitle>Actions</SectionTitle>
      <Panel note="There is no release control. Release is a two-person action: one qualified person signs, a different one countersigns, and it still executes only with the correct role and zero open gates.">
        {can('release_product') && (
          <div className="approval">
            {approval ? (
              <>
                <Callout tone="warn" title="Awaiting a second approver">
                  {approval.first_by} signed at {dateTime(approval.first_at)}. Nothing has been
                  released. This approval lapses at {dateTime(approval.expires_at)}.
                  {approval.justification && <div style={{ marginTop: 6 }}>“{approval.justification}”</div>}
                </Callout>
                {approval.can_countersign ? (
                  <div className="row">
                    <input
                      className="field"
                      style={{ maxWidth: 280 }}
                      type="text"
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
                ) : (
                  <p className="panel__note" style={{ marginBottom: 0 }}>{approval.blocked_reason}</p>
                )}
              </>
            ) : (
              <div className="row">
                <input
                  className="field"
                  style={{ maxWidth: 240 }}
                  type="text"
                  value={signature}
                  placeholder="Type your name to sign"
                  onChange={(e) => setSignature(e.target.value)}
                />
                <input
                  className="field"
                  style={{ maxWidth: 320 }}
                  type="text"
                  value={justification}
                  placeholder="Why this lot is releasable"
                  onChange={(e) => setJustification(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn--outline"
                  disabled={signature.trim().length < 4}
                  onClick={signFirst}
                >
                  Sign as first approver
                </button>
              </div>
            )}
          </div>
        )}
        <div className="row">
          {onOpenPacket && (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => onOpenPacket(journey.patient_key)}
            >
              Open reviewer packet
            </button>
          )}
          {can('merge_identity') && (
            <button type="button" className="btn btn--outline" onClick={proposeLink}>
              Propose identity link
            </button>
          )}
          <button type="button" className="btn btn--ghost" onClick={() => onRunAgent('AG-EXPLAIN', journey.patient_key)}>
            Explain this verdict
          </button>
        </div>
        {!can('release_product') && !can('merge_identity') && (
          <p className="panel__note" style={{ marginTop: 10, marginBottom: 0 }}>
            This view is read-only for your role. Release belongs to Quality and identity linking to
            the Identity adjudicator.
          </p>
        )}
      </Panel>

      <SectionTitle>Access applied to this view</SectionTitle>
      <Panel>
        <DefinitionList
          wide
          items={[
            ['Role', label(access.role)],
            ['Purpose', label(access.purpose)],
            ['Gates satisfied', percent(readiness.confidence)],
            ['Fields withheld', access.redacted_fields.length
              ? <span className="mono subtle">{access.redacted_fields.join(', ')}</span>
              : <span className="subtle">None</span>],
          ]}
        />
      </Panel>

      <SectionTitle>Evidence consulted</SectionTitle>
      <Panel>
        <div className="row">
          {readiness.evidence_references.map((ref) => <Tag key={ref}>{ref}</Tag>)}
        </div>
      </Panel>
    </>
  );
}
