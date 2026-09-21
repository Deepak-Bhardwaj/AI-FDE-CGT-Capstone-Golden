import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Callout, Loading, Panel, Redactable, SectionTitle, Status, Tag } from '../components/ui';
import { dateTime, label } from '../lib/format';

const DAY = 24;

function duration(hours) {
  if (hours === null || hours === undefined) return '—';
  if (hours < DAY) return `${Math.round(hours)} h`;
  return `${(hours / DAY).toFixed(1)} days`;
}

function day(iso) {
  return iso ? dateTime(iso).slice(0, 11) : '—';
}

export default function PatientTimeline({ patientKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    setError('');
    api.get(`/api/workflow/${patientKey}/timeline`).then(({ ok, data: payload }) => {
      if (ok) setData(payload);
      else setError(payload.detail || `No timeline for ${patientKey}.`);
    });
  }, [patientKey]);

  if (error) return <Callout tone="fail" title="Unavailable">{error}</Callout>;
  if (!data) return <Loading />;

  const projection = data.projection;

  return (
    <>
      <section className={`jhero jhero--${data.readiness}`}>
        <div className="jhero__main">
          <div className="jhero__idline">
            <span className="jhero__name">
              <Redactable value={data.patient_name} fallback="Name not recorded" />
            </span>
            <Status value={data.readiness} />
          </div>
          <div className="jhero__facts">
            <div className="jfact">
              <span className="jfact__label">Patient</span>
              <span className="jfact__value mono">{data.patient_key}</span>
            </div>
            <div className="jfact">
              <span className="jfact__label">Treatment centre</span>
              <span className="jfact__value mono">{data.centre}</span>
            </div>
          </div>
        </div>

        {projection && (
          <div className="jhero__progress">
            <div className="jprog__head">
              <span className="jprog__count">
                {projection.completed_milestones}<small>/{projection.total_milestones}</small>
              </span>
              <span className="jprog__label">milestones recorded</span>
            </div>
            <div className="jprog__track">
              <span
                className="jprog__fill"
                style={{ width: `${(projection.completed_milestones / projection.total_milestones) * 100}%` }}
              />
            </div>
            <div className="jprog__pips" aria-hidden="true">
              {projection.steps.map((s) => (
                <span
                  key={s.stage_id}
                  className={`jpip jpip--${s.actual_at || s.released ? 'COMPLETE' : s.predicted ? 'WAITING' : 'NOT_STARTED'}`}
                  title={s.label}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      <Callout tone="info" title="What this page is">
        A plain-language view of where this therapy has got to and when the remaining steps are
        likely to happen. The dates are estimates drawn from how long these steps have taken for
        comparable patients — they are not appointments, and the care team confirms every date.
      </Callout>

      {projection?.predicted_completion && !projection.already_complete && (
        <Panel title={`When the therapy is likely to be ${projection.predicted_completion_label ? projection.predicted_completion_label.toLowerCase() : 'ready'}`}>
          <div className="estimate">
            <div className="estimate__band">
              <span className="estimate__label">Earliest</span>
              <span className="estimate__value">{day(projection.predicted_completion.earliest)}</span>
            </div>
            <div className="estimate__band estimate__band--main">
              <span className="estimate__label">Most likely</span>
              <span className="estimate__value">{day(projection.predicted_completion.expected)}</span>
            </div>
            <div className="estimate__band">
              <span className="estimate__label">Latest</span>
              <span className="estimate__value">{day(projection.predicted_completion.latest)}</span>
            </div>
          </div>
          <p className="panel__note" style={{ marginTop: 12, marginBottom: 0 }}>
            {data.advisory.summary}
          </p>
        </Panel>
      )}

      {data.waiting_on.length > 0 && (
        <Callout tone="warn" title="What is being worked on right now">
          <ul className="steps" style={{ marginTop: 4 }}>
            {data.waiting_on.map((gate) => (
              <li key={gate.gate_id}>
                {gate.name} — with {gate.authority} ({label(gate.status)})
              </li>
            ))}
          </ul>
          Until these are settled the dates above cannot be met.
        </Callout>
      )}

      <SectionTitle>Step by step</SectionTitle>
      <Panel note="Recorded times come from the source systems. Typical duration is the median for comparable journeys in this estate.">
        <div className="tl">
          {projection?.steps.map((step) => (
            <div
              key={step.stage_id}
              className={`tl__row tl__row--${step.actual_at || step.released ? 'done' : 'ahead'}`}
            >
              <div className="tl__mark"><i /></div>
              <div className="tl__body">
                <div className="tl__name">
                  {step.label}
                  {step.actual_at || step.released
                    ? <Status value="PASS">Done</Status>
                    : <Status value="UNKNOWN">Still to come</Status>}
                </div>
                <div className="tl__when">
                  {step.actual_at ? (
                    <>
                      <strong>{dateTime(step.actual_at)}</strong>
                      {step.elapsed_from_enrolment_h !== null &&
                        ` · ${duration(step.elapsed_from_enrolment_h)} after enrolment`}
                    </>
                  ) : step.predicted ? (
                    <>
                      <strong>{day(step.predicted.expected)}</strong> expected ·{' '}
                      {day(step.predicted.earliest)} to {day(step.predicted.latest)} ·{' '}
                      {step.predicted.anchored_on === 'recorded event'
                        ? 'measured from the last recorded event'
                        : 'measured from the previous estimate, so less certain'}
                    </>
                  ) : (
                    <span className="subtle">{step.note || 'No comparable history to estimate from.'}</span>
                  )}
                </div>
                <div className="tl__meta">
                  Typical: {duration(step.expected_hours)} · {step.expected_basis}
                  {step.variance_hours !== null && step.variance_hours !== undefined && (
                    <span className={step.variance_hours > 0 ? 'tl__late' : 'tl__early'}>
                      {' · '}
                      {step.variance_hours > 0
                        ? `${duration(step.variance_hours)} slower than typical`
                        : `${duration(Math.abs(step.variance_hours))} faster than typical`}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <SectionTitle>How this estimate was made</SectionTitle>
      <Panel>
        <div className="row" style={{ marginBottom: 10 }}>
          <Tag>{data.advisory.agent_id}</Tag>
          <Tag>Class {data.advisory.action_class} — advisory</Tag>
          <Tag>{projection?.model?.name} {projection?.model?.version}</Tag>
          <Tag>Confidence {Math.round((data.advisory.confidence || 0) * 100)}%</Tag>
          <span className="subtle">Generated {dateTime(data.advisory.generated_at)}</span>
        </div>
        <p className="panel__note" style={{ margin: 0 }}>{projection?.model?.method}.</p>
        <Callout tone="warn" title="Limits of this forecast">{data.advisory.uncertainty}</Callout>
      </Panel>
    </>
  );
}
