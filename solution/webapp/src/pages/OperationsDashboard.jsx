import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Loading, Panel } from '../components/ui';
import { label } from '../lib/format';

const GATE_NAMES = {
  G1: 'Identity & chain of identity',
  G2: 'Consent',
  G3: 'Payer authorization',
  G4: 'Treatment centre controls',
  G5: 'Manufacturing complete',
  G6: 'QC evidence',
  G7: 'Deviations dispositioned',
  G8: 'QA release approved',
  G9: 'Return custody',
  G10: 'Clinical prerequisites',
};

export default function OperationsDashboard() {
  const [data, setData] = useState(null);
  const [insight, setInsight] = useState(null);

  useEffect(() => {
    api.get('/api/overview').then((r) => setData(r.data));
    api.post('/api/agents/AG-TRIAGE/invoke', { subject: '' })
      .then(({ ok, data: payload }) => ok && setInsight(payload.result));
  }, []);

  if (!data) return <Loading />;

  const readiness = data.readiness || {};
  const failures = Object.entries(data.gate_failures || {}).sort((a, b) => b[1] - a[1]);
  const peak = Math.max(...failures.map(([, n]) => n), 1);
  const totalReadiness = Object.values(readiness).reduce((sum, n) => sum + n, 0) || 1;

  return (
    <>
      {insight && (
        <div className="insight">
          <span className="insight__spark" aria-hidden="true">✦</span>
          <div className="insight__body">
            <div className="insight__label">AI insight · advisory</div>
            <div className="insight__text">{insight.summary}</div>
          </div>
          <span className="insight__meta">{insight.agent_id} · {Math.round(insight.confidence * 100)}%</span>
        </div>
      )}

      <div className="kpis">
        <div className="kpi kpi--fail">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">▲</span>
            <span className="kpi__label">Legacy declared ready</span>
          </div>
          <div className="kpi__value">{data.legacy_declared_ready}</div>
          <div className="kpi__caption">Journeys passing the legacy <code>patient_ready()</code> rule</div>
        </div>

        <div className="kpi kpi--pass">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">✓</span>
            <span className="kpi__label">Governed declared ready</span>
          </div>
          <div className="kpi__value">{data.governed_declared_ready}</div>
          <div className="kpi__caption">All ten readiness gates satisfied</div>
        </div>

        <div className="kpi kpi--fail kpi--wide">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">⊘</span>
            <span className="kpi__label">Unsafe readiness blocked</span>
          </div>
          <div className="kpi__value">{data.divergence?.legacy_says_ready_but_qa_has_not_released}</div>
          <div className="kpi__caption">ERP or MES imply availability while Quality has not released</div>
        </div>

        <div className="kpi kpi--warn">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">⊙</span>
            <span className="kpi__label">Identity adjudications</span>
          </div>
          <div className="kpi__value">{data.identity_queue}</div>
          <div className="kpi__caption">Routed to a human — none merged automatically</div>
        </div>

        <div className="kpi kpi--fail">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">⚑</span>
            <span className="kpi__label">Released with unresolved QC</span>
          </div>
          <div className="kpi__value">{data.release_integrity?.released_with_unresolved_qc}</div>
          <div className="kpi__caption">Historical records requiring a QA retrospective</div>
        </div>

        <div className="kpi kpi--warn">
          <div className="kpi__top">
            <span className="kpi__icon" aria-hidden="true">✉</span>
            <span className="kpi__label">Identity signals in email only</span>
          </div>
          <div className="kpi__value">{data.coi_from_email}</div>
          <div className="kpi__caption">Invisible to every structured data check</div>
        </div>
      </div>

      <div className="dash-grid">
        <Panel
          title="Readiness distribution"
          note={`Sampled across ${data.sampled} journeys under policy ${data.policy_version}.`}
        >
          <div className="stackbar" role="img" aria-label="Readiness distribution">
            {Object.entries(readiness).map(([state, count]) => (
              count > 0 ? (
                <span
                  key={state}
                  className={`stackbar__seg stackbar__seg--${state}`}
                  style={{ width: `${(count / totalReadiness) * 100}%` }}
                  title={`${label(state)}: ${count}`}
                />
              ) : null
            ))}
          </div>

          <div className="legend">
            {Object.entries(readiness).map(([state, count]) => (
              <div key={state} className="legend__item">
                <span className={`legend__dot legend__dot--${state}`} aria-hidden="true" />
                <span className="legend__text">
                  <span className="legend__label">{label(state)}</span>
                  <span className="legend__value">
                    {count}
                    <small>· {Math.round((count / totalReadiness) * 100)}%</small>
                  </span>
                </span>
              </div>
            ))}
          </div>

          <p className="panel__note" style={{ marginTop: 18 }}>
            No journey reaches <strong>Ready</strong> because gate G10 — clinical prerequisites — has no
            authoritative source system in this estate. Reporting a pass there would fabricate evidence.
          </p>
        </Panel>

        <Panel
          title="Where journeys are blocked"
          note="Sampled journeys failing or conflicting at each readiness gate, worst first."
        >
          <div className="gatebars">
            {failures.map(([gate, count]) => (
              <div key={gate} className="gatebar">
                <div className="gatebar__head">
                  <span className="gatebar__id">{gate}</span>
                  <span className="gatebar__name">{GATE_NAMES[gate]}</span>
                  <span className="gatebar__count">{count}</span>
                </div>
                <div className="gatebar__track">
                  <span
                    className={`gatebar__fill${count >= peak * 0.75 ? ' gatebar__fill--hot' : ''}`}
                    style={{ width: `${(count / peak) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
