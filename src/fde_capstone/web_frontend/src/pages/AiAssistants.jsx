import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import {
  Callout, DataTable, DefinitionList, Loading, Panel, SectionTitle, Status, Tag,
} from '../components/ui';
import { label, percent, shortTime } from '../lib/format';

// A stylized glyph and accent per assistant, purely visual — the contract underneath is identical.
const AGENT_STYLE = {
  'AG-EXPLAIN': { glyph: '◈', accent: 'violet' },
  'AG-IDENTITY': { glyph: '⬡', accent: 'blue' },
  'AG-TRIAGE': { glyph: '▲', accent: 'amber' },
  'AG-FORECAST': { glyph: '◔', accent: 'teal' },
  'AG-JOURNEY': { glyph: '◷', accent: 'teal' },
  'AG-ROUTE': { glyph: '➤', accent: 'blue' },
  'AG-EXTRACT': { glyph: '✦', accent: 'violet' },
};
const DEFAULT_STYLE = { glyph: '◈', accent: 'violet' };

export default function AiAssistants({ onRunAgent, patientKey }) {
  const [catalogue, setCatalogue] = useState(null);
  const [activity, setActivity] = useState(null);
  const [subjects, setSubjects] = useState({});
  const [running, setRunning] = useState(null);
  const [reconKey, setReconKey] = useState(patientKey || 'P-00005');
  const [recon, setRecon] = useState(null);
  const [reconBusy, setReconBusy] = useState(false);
  const [reconError, setReconError] = useState('');

  const loadActivity = useCallback(() => {
    api.get('/api/agents/activity?limit=25').then((r) => setActivity(r.data));
  }, []);

  useEffect(() => {
    api.get('/api/agents').then((r) => setCatalogue(r.data));
    loadActivity();
  }, [loadActivity]);

  const run = async (agentId, subject) => {
    setRunning(agentId);
    await onRunAgent(agentId, subject);
    setRunning(null);
    loadActivity();
  };

  const reconcile = async (event) => {
    event.preventDefault();
    setReconBusy(true);
    setReconError('');
    const { ok, data } = await api.post('/api/reconciliation/patient', { patient_key: reconKey.trim() });
    setReconBusy(false);
    if (!ok) {
      setRecon(null);
      setReconError(data.detail || 'Reconciliation was refused.');
      return;
    }
    setRecon(data);
  };

  const reconPanel = (
    <section className="recon-card">
      <div className="recon-card__head">
        <div>
          <div className="twin-widget__eyebrow">Identity reconciliation</div>
          <h2 className="panel__title" style={{ margin: '4px 0 0' }}>Resolve a patient across CRM, clinical and orchestration</h2>
        </div>
      </div>
      <form className="recon-form" onSubmit={reconcile}>
        <label className="signin__field" style={{ flex: 1, minWidth: 220 }}>
          <span>Patient key</span>
          <input
            className="field mono"
            value={reconKey}
            onChange={(e) => setReconKey(e.target.value)}
            placeholder="P-00005"
            aria-label="Patient key to reconcile"
          />
        </label>
        <button type="submit" className="btn btn--primary" disabled={reconBusy || !reconKey.trim()}>
          {reconBusy ? 'Resolving…' : 'Reconcile identity'}
        </button>
      </form>
      {reconError && <Callout tone="fail">{reconError}</Callout>}
      {recon && (
        <div className="recon-result">
          <div className="twin-widget__score">
            <span>{Math.round((recon.confidence_score || 0) * 100)}</span>
            <small>confidence</small>
          </div>
          <div className="recon-result__body">
            <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
              <span className="mono">{recon.resolved_patient_key || recon.patient_key || '—'}</span>
              <Status value={recon.requires_human_review ? 'CONFLICT' : 'PASS'}>
                {recon.requires_human_review ? 'HITL required' : 'Aligned'}
              </Status>
              <Tag>Action: {recon.autonomous_action || 'none'}</Tag>
            </div>
            <p className="panel__note" style={{ margin: '8px 0 0' }}>{recon.note}</p>
            {(recon.conflicts || []).length > 0 && (
              <div className="exc-card__drivers" style={{ marginTop: 10 }}>
                {recon.conflicts.map((conflict, index) => (
                  <span key={index} className="exc-card__chip">
                    {conflict.type || JSON.stringify(conflict)}
                  </span>
                ))}
              </div>
            )}
            {(recon.evidence || []).length > 0 && (
              <div className="recon-evidence">
                {recon.evidence.slice(0, 6).map((item, index) => (
                  <div key={index} className="recon-evidence__row">
                    <span className="mono">{item.source || item.path}</span>
                    <span className="subtle">{item.field} = {String(item.value ?? '—')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );

  if (!catalogue) {
    return (
      <>
        {reconPanel}
        <Loading />
      </>
    );
  }

  return (
    <>
      <div className="ai-hero">
        <div className="ai-hero__orb" aria-hidden="true"><span /><span /><span /></div>
        <div className="ai-hero__body">
          <div className="ai-hero__eyebrow">Deterministic control plane · advisory intelligence</div>
          <p className="ai-hero__lede">{catalogue.principle}</p>
          <div className="row" style={{ marginTop: 14 }}>
            <Tag>Model: {catalogue.model.name} {catalogue.model.version}</Tag>
            <Tag>Prompts: {catalogue.model.prompt_version}</Tag>
            <span className={`ai-pulse ai-pulse--${catalogue.model.llm_configured ? 'on' : 'off'}`}>
              <i />{catalogue.model.llm_configured ? 'Language model configured' : 'Running fully local — no language model configured'}
            </span>
          </div>
        </div>
      </div>

      {reconPanel}

      <div className="ai-grid">
        {catalogue.agents.map((agent) => {
          const style = AGENT_STYLE[agent.agent_id] || DEFAULT_STYLE;
          const busy = running === agent.agent_id;
          return (
            <div key={agent.agent_id} className={`ai-card ai-card--${style.accent}`}>
              <div className="ai-card__head">
                <div className="ai-card__glyph">{style.glyph}</div>
                <div>
                  <div className="ai-card__name">{agent.name}</div>
                  <div className="ai-card__id">{agent.agent_id}</div>
                </div>
                <span className="ai-card__class">Class {agent.action_class}</span>
              </div>

              <p className="ai-card__purpose">{agent.purpose}</p>

              <DefinitionList
                items={[
                  ['Decision authority', agent.authority],
                  ['Permitted callers', agent.contract.allowed_callers.map((c) => <Tag key={c}>{label(c)}</Tag>)],
                  ['Data classification', <span className="mono">{agent.contract.data_classification}</span>],
                  ['Side effects', <span style={{ color: 'var(--pass)', fontWeight: 600 }}>{agent.contract.side_effects}</span>],
                  ['Approval required', agent.contract.approval_required],
                ]}
              />

              <div className="ai-card__prohibited">
                <div className="subtle" style={{ marginBottom: 4 }}>This assistant may not:</div>
                {agent.prohibited.map((item) => (
                  <div key={item} className="ai-card__prohibited-item">✕ {item}</div>
                ))}
              </div>

              <form
                className="ai-runbar"
                onSubmit={(e) => { e.preventDefault(); run(agent.agent_id, subjects[agent.agent_id] ?? patientKey); }}
              >
                <input
                  className="field ai-runbar__input"
                  value={subjects[agent.agent_id] ?? patientKey}
                  onChange={(e) => setSubjects({ ...subjects, [agent.agent_id]: e.target.value })}
                  aria-label={`Subject for ${agent.name}`}
                  disabled={busy}
                />
                <button type="submit" className="ai-runbar__btn" disabled={busy}>
                  {busy ? <span className="ai-spinner" /> : '▶'}
                  {busy ? 'Thinking…' : 'Run'}
                </button>
              </form>
            </div>
          );
        })}
      </div>

      <SectionTitle>Actions with no assistant, by design</SectionTitle>
      <Panel
        note="These are consequential actions. No tool is registered for any of them — the absence is the control, and it is auditable here."
        flush
      >
        <DataTable
          columns={[
            { key: 'action', header: 'Action', render: (r) => <span className="mono">{r.action}</span> },
            { key: 'authority', header: 'Decision authority' },
            { key: 'agent', header: 'Assistant', render: () => <Status value="FAIL">None registered</Status> },
          ]}
          rows={catalogue.no_agent_by_design.map((r) => ({ ...r, id: r.action }))}
        />
      </Panel>

      <SectionTitle>Assistant activity</SectionTitle>
      <Panel flush>
        {(activity?.activity || []).length === 0 ? (
          <div className="empty">No assistant has been run in this session.</div>
        ) : (
          <div className="ai-feed">
            {activity.activity.map((r, i) => {
              const style = AGENT_STYLE[r.agent_id] || DEFAULT_STYLE;
              return (
                <div key={i} className={`ai-feed__row ai-feed__row--${style.accent}`}>
                  <div className="ai-feed__glyph">{style.glyph}</div>
                  <div className="ai-feed__body">
                    <div className="ai-feed__meta">
                      <span className="mono">{r.agent_id}</span>
                      <Status value="UNKNOWN">Class {r.action_class}</Status>
                      <span className="subtle">{r.subject || 'whole cohort'}</span>
                      <span className="subtle">{shortTime(r.invoked_at)}</span>
                    </div>
                    <div className="ai-feed__summary">{r.summary}</div>
                    <div className="ai-confidence" title={`Confidence ${percent(r.confidence)}`}>
                      <span style={{ width: `${Math.round((r.confidence || 0) * 100)}%` }} />
                    </div>
                  </div>
                  <div className="ai-feed__side">
                    <span className="ai-feed__pct">{percent(r.confidence)}</span>
                    <Status value="PASS">Not applied</Status>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </>
  );
}

export function AgentResultDetail({ result }) {
  if (!result) return <Loading />;
  const style = AGENT_STYLE[result.agent_id] || DEFAULT_STYLE;

  return (
    <>
      <div className={`ai-answer ai-answer--${style.accent}`}>
        <div className="ai-answer__head">
          <div className="ai-card__glyph">{style.glyph}</div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <Status value="UNKNOWN">Advisory · Class {result.action_class}</Status>
            <Tag>{result.subject || 'Whole cohort'}</Tag>
            <Status value="PASS">Applied automatically: no</Status>
          </div>
        </div>
        <div className="ai-answer__summary">{result.summary}</div>
        <div className="ai-confidence ai-confidence--lg" title={`Confidence ${percent(result.confidence)}`}>
          <span style={{ width: `${Math.round((result.confidence || 0) * 100)}%` }} />
        </div>
        <div className="subtle" style={{ marginTop: 4 }}>Confidence {percent(result.confidence)}</div>
      </div>

      <SectionTitle>Stated uncertainty</SectionTitle>
      <Callout tone="warn">{result.uncertainty}</Callout>

      {result.findings?.length > 0 && (
        <>
          <SectionTitle>Findings</SectionTitle>
          <Panel flush>
            <DataTable
              columns={Object.keys(result.findings[0]).map((key) => ({
                key,
                header: label(key),
                render: (row) => {
                  const value = row[key];
                  if (value === null || value === undefined) return '—';
                  if (typeof value === 'object') return <span className="mono">{JSON.stringify(value)}</span>;
                  return <span style={{ fontSize: 14.5 }}>{String(value)}</span>;
                },
              }))}
              rows={result.findings.map((f, i) => ({ ...f, id: i }))}
            />
          </Panel>
        </>
      )}

      <SectionTitle>Supporting evidence</SectionTitle>
      <Panel flush>
        <DataTable
          columns={[
            { key: 'source', header: 'Source system', render: (r) => <span className="mono">{r.source}</span> },
            { key: 'fact', header: 'Fact', render: (r) => <span className="mono">{r.fact}</span> },
            { key: 'value', header: 'Value', render: (r) => <span style={{ fontSize: 14.5 }}>{typeof r.value === 'object' ? JSON.stringify(r.value) : String(r.value)}</span> },
            { key: 'ref', header: 'Reference', render: (r) => <span className="mono subtle">{r.ref}</span> },
            { key: 'trust', header: 'Trust', render: (r) => <Status value={r.trust} /> },
          ]}
          rows={result.evidence.map((e, i) => ({ ...e, id: i }))}
          empty="No evidence was cited."
        />
      </Panel>

      <SectionTitle>Provenance</SectionTitle>
      <Panel>
        <DefinitionList
          wide
          items={[
            ['Authority required to act', result.required_authority],
            ['Model', <span className="mono">{result.model.name} {result.model.version}</span>],
            ['Prompt version', <span className="mono">{result.model.prompt_version}</span>],
            ['Run at', <span className="mono">{result.invoked_at}</span>],
            ['Applied automatically', <Status value="PASS">No</Status>],
          ]}
        />
      </Panel>
    </>
  );
}
