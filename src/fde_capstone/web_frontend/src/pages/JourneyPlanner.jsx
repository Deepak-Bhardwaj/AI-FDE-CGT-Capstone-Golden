import { useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import JourneyFlow, { day } from '../components/JourneyFlow';
import { Callout, Loading, Panel, SectionTitle, Tag } from '../components/ui';
import { dateTime } from '../lib/format';

export default function JourneyPlanner() {
  const today = new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState(today);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [playToken, setPlayToken] = useState(0);

  const load = async (date) => {
    setData(null);
    setError('');
    const { ok, data: payload } = await api.get(`/api/planning/projection?start=${date}`);
    if (!ok) {
      setError(refusalReason(payload));
      return;
    }
    setData(payload);
    setPlayToken((n) => n + 1);
  };

  useEffect(() => { load(today); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const projection = data?.projection;

  return (
    <>
      <div className="filterbar">
        <label className="planner__field">
          <span>Planned enrolment date</span>
          <input
            className="field"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            aria-label="Planned enrolment date"
          />
        </label>
        <button type="button" className="btn btn--primary" onClick={() => load(start)}>
          Project the journey
        </button>
        {projection && (
          <button
            type="button"
            className="btn btn--outline"
            onClick={() => setPlayToken((n) => n + 1)}
          >
            ▶ Replay
          </button>
        )}
      </div>

      {error && <Callout tone="fail" title="Unavailable">{error}</Callout>}
      {!projection && !error && <Loading />}

      {projection && (
        <>
          <Callout tone="info" title="A planning aid, not a schedule">
            Nothing is known about this patient yet, so this is how this estate's own journeys have
            actually run, rolled forward from {day(projection.start)}. No capacity, clinical or
            payer check has been made. Never quote these dates to a patient.
          </Callout>

          <Panel title="Expected shape of the journey">
            <div className="estimate">
              <div className="estimate__band">
                <span className="estimate__label">Best case</span>
                <span className="estimate__value">{day(projection.ready_window.earliest)}</span>
              </div>
              <div className="estimate__band estimate__band--main">
                <span className="estimate__label">Most likely release</span>
                <span className="estimate__value">{day(projection.ready_window.expected)}</span>
              </div>
              <div className="estimate__band">
                <span className="estimate__label">Slow case</span>
                <span className="estimate__value">{day(projection.ready_window.latest)}</span>
              </div>
              <div className="estimate__band">
                <span className="estimate__label">Vein-to-release</span>
                <span className="estimate__value">{projection.expected_total_days} days</span>
              </div>
            </div>
          </Panel>

          <SectionTitle>The journey, step by step</SectionTitle>
          <Panel note="Each step appears as it would occur. Press Replay to run it again.">
            <JourneyFlow steps={projection.steps} playToken={playToken} />
          </Panel>

          <SectionTitle>How this was produced</SectionTitle>
          <Panel>
            <div className="row" style={{ marginBottom: 10 }}>
              <Tag>{data.advisory.agent_id}</Tag>
              <Tag>Class {data.advisory.action_class} — advisory</Tag>
              <Tag>{projection.model.name} {projection.model.version}</Tag>
              <Tag>Confidence {Math.round(data.advisory.confidence * 100)}%</Tag>
              <span className="subtle">Generated {dateTime(data.advisory.generated_at)}</span>
            </div>
            <p className="panel__note" style={{ margin: 0 }}>{projection.model.method}.</p>
            <Callout tone="warn" title="Limits">{data.advisory.uncertainty}</Callout>
          </Panel>
        </>
      )}
    </>
  );
}
