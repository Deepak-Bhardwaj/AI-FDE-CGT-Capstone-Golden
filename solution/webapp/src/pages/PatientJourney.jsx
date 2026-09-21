import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Callout, DataTable, Loading, Panel, Redactable, Status, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

const EXAMPLE = { key: 'P-00005', note: 'Blocked at centre qualification and QA release' };

export default function PatientJourney({ patientKey, onPatientKeyChange, onOpenReadiness, onOpenAction, onRunAgent }) {
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState(null);
  const [journey, setJourney] = useState(null);
  const [pipeline, setPipeline] = useState(null);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setJourney(null);
    setError(null);
    api.get(`/api/workflow/${patientKey}`).then(({ ok, data }) => {
      if (!active) return;
      if (ok) setJourney(data);
      else setError(data.detail || `No journey found for ${patientKey}.`);
    });
    return () => { active = false; };
  }, [patientKey, reloadToken]);

  useEffect(() => {
    api.get('/api/workflow').then((r) => setPipeline(r.data));
  }, []);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setMatches(null);
      return undefined;
    }
    const timer = setTimeout(() => {
      api.get(`/api/journeys?q=${encodeURIComponent(term)}&limit=8`)
        .then((r) => setMatches(r.data.journeys || []));
    }, 220);
    return () => clearTimeout(timer);
  }, [query]);

  const open = (key) => {
    setQuery('');
    setMatches(null);
    if (key === patientKey) setReloadToken((n) => n + 1);
    else onPatientKeyChange(key);
  };

  return (
    <>
      <div className="filterbar">
        <div className="search inputwrap">
          <span className="inputwrap__icon" aria-hidden="true">⌕</span>
          <input
            className="field inputwrap__field"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search patients by identifier or name"
            aria-label="Search patients"
          />
          {matches && (
            <div className="search__results">
              {matches.length === 0 ? (
                <div className="search__empty">No patient matches “{query.trim()}”.</div>
              ) : (
                matches.map((m) => (
                  <button key={m.patient_key} type="button" className="search__hit" onClick={() => open(m.patient_key)}>
                    <span className="search__name"><Redactable value={m.patient_name} fallback="Name not recorded" /></span>
                    <span className="mono subtle">{m.patient_key}</span>
                    <Status value={m.readiness} />
                  </button>
                ))
              )}
            </div>
          )}
        </div>
        <button type="button" className="btn btn--primary" onClick={() => open(patientKey)}>
          Refresh journey
        </button>
        {journey && (
          <>
            <button type="button" className="btn btn--outline" onClick={() => onOpenReadiness(patientKey)}>
              Readiness detail
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => onRunAgent('AG-EXPLAIN', patientKey)}>
              Explain the blockage
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => onRunAgent('AG-FORECAST', patientKey)}>
              Forecast release
            </button>
          </>
        )}
      </div>

      <div className="row" style={{ marginBottom: 20, gap: 8 }}>
        <span className="subtle">Example:</span>
        <button
          type="button"
          title={EXAMPLE.note}
          className={`btn btn--sm ${EXAMPLE.key === patientKey ? 'btn--dark' : 'btn--outline'}`}
          onClick={() => open(EXAMPLE.key)}
        >
          {EXAMPLE.key}
        </button>
        <span className="subtle">{EXAMPLE.note}</span>
      </div>

      {error && <Callout tone="fail" title="Not found">{error}</Callout>}
      {!journey && !error && <Loading />}

      {journey && (
        <>
          <section className={`jhero jhero--${journey.readiness}`}>
            <div className="jhero__main">
              <div className="jhero__idline">
                <span className="jhero__key">{patientKey}</span>
                <Status value={journey.readiness} />
                {journey.batch_id && <Tag>{journey.batch_id}</Tag>}
              </div>
              <div className="jhero__facts">
                <div className="jfact">
                  <span className="jfact__label">Governed state</span>
                  <span className="jfact__value">{label(journey.governed_state)}</span>
                </div>
                <div className="jfact">
                  <span className="jfact__label">Legacy status</span>
                  <span className="jfact__value">{label(journey.legacy_status)}</span>
                </div>
                <div className="jfact">
                  <span className="jfact__label">Policy</span>
                  <span className="jfact__value mono">{journey.policy_version}</span>
                </div>
              </div>
            </div>

            <div className="jhero__progress">
              <div className="jprog__head">
                <span className="jprog__count">
                  {journey.completed_stages}<small>/{journey.total_stages}</small>
                </span>
                <span className="jprog__label">stages complete</span>
              </div>
              <div className="jprog__track">
                <span
                  className="jprog__fill"
                  style={{ width: `${(journey.completed_stages / journey.total_stages) * 100}%` }}
                />
              </div>
              <div className="jprog__pips" aria-hidden="true">
                {journey.stages.map((s) => (
                  <span key={s.stage_id} className={`jpip jpip--${s.status}`} title={`${s.seq}. ${s.name}`} />
                ))}
              </div>
            </div>
          </section>

          {journey.current_stage && (
            <div className={`nowcard nowcard--${journey.current_stage.status === 'CONFLICT' ? 'conflict' : 'fail'}`}>
              <div className="nowcard__side">
                <span className="nowcard__eyebrow">Current blocking stage</span>
                <span className="nowcard__seq">{journey.current_stage.seq}</span>
              </div>
              <div className="nowcard__body">
                <h3 className="nowcard__title">{journey.current_stage.name}</h3>
                <p className="nowcard__detail">{journey.current_stage.detail}</p>
                {journey.current_stage.handling && (
                  <div className="nowcard__handled">
                    <strong>{label(journey.current_stage.handling.state)}</strong> by{' '}
                    {journey.current_stage.handling.by} · {dateTime(journey.current_stage.handling.at)}
                  </div>
                )}
                {journey.current_stage.next_action && (
                  <div className="nowcard__cta">
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      onClick={() => onOpenAction(patientKey, journey.current_stage)}
                    >
                      {journey.current_stage.next_action}
                    </button>
                    <span className="muted">Authority: {journey.current_stage.action_authority}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <Panel
            title="Vein-to-vein journey"
            note="Each stage is derived from source evidence and the readiness gates. A later stage can read as complete while an earlier one is unresolved: the source systems recorded the material moving on regardless, and that divergence is called out on the stage."
          >
            <div className="rail">
              {journey.stages.map((stage) => (
                <div key={stage.stage_id} className={`rail__step rail__step--${stage.status}`}>
                  <div className="rail__seq">{stage.seq}</div>
                  <div className="rail__mark"><i /></div>
                  <div className="rail__body">
                    <div className="rail__name">
                      {stage.name}
                      <Status value={stage.status} />
                      {stage.gate_ids.map((g) => <Tag key={g}>{g}</Tag>)}
                    </div>
                    {stage.detail && <div className="rail__detail">{stage.detail}</div>}
                    <div className="rail__meta">
                      Owner: {stage.owner}
                      {stage.occurred_at && ` · ${dateTime(stage.occurred_at)}`}
                      {stage.evidence_refs?.length > 0 &&
                        ` · Evidence: ${stage.evidence_refs.slice(0, 2).join(', ')}`}
                    </div>
                    {stage.proceeded_despite?.length > 0 && (
                      <div className="rail__breach">
                        Moved on while {stage.proceeded_despite.join(', ')} was still unresolved —
                        the source systems did not enforce this order.
                      </div>
                    )}
                    {stage.handling && (
                      <div className={`rail__handled rail__handled--${stage.handling.state}`}>
                        {label(stage.handling.state)} by {stage.handling.by} ·{' '}
                        {dateTime(stage.handling.at)}
                        {stage.attestation
                          ? ' · electronically signed, gate cleared on attestation'
                          : ' · owned, but the gate stays red until the evidence is corrected'}
                      </div>
                    )}
                    {(stage.next_action || stage.attestation) && (
                      <button
                        type="button"
                        className="rail__action"
                        onClick={() => onOpenAction(patientKey, stage)}
                        title={`Open the action for ${stage.name}`}
                      >
                        {stage.next_action
                          ? `▸ ${stage.next_action} — ${stage.action_authority}`
                          : `▸ Cleared on attestation by ${stage.attestation.by} — review or withdraw`}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}

      {pipeline && (
        <Panel
          title="Cohort pipeline"
          note={`Where ${pipeline.sampled} journeys are currently sitting, by stage.`}
          flush
        >
          <DataTable
            columns={[
              {
                key: 'name',
                header: 'Stage',
                render: (row) => (
                  <>
                    <span className="mono subtle">{row.stage_id}</span> {row.name}
                  </>
                ),
              },
              ...['COMPLETE', 'ACTIVE', 'WAITING', 'BLOCKED', 'CONFLICT', 'HALTED', 'NOT_STARTED'].map(
                (state) => ({
                  key: state,
                  header: label(state),
                  align: 'right',
                  render: (row) =>
                    row.counts[state] ? (
                      <Status value={state}>{row.counts[state]}</Status>
                    ) : (
                      <span className="subtle">—</span>
                    ),
                }),
              ),
            ]}
            rows={pipeline.stages.map((s) => ({ ...s, id: s.stage_id }))}
          />
        </Panel>
      )}
    </>
  );
}
