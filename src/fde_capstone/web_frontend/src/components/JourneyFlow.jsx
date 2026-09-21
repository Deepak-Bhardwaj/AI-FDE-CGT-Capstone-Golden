import { useEffect, useState } from 'react';
import { dateTime } from '../lib/format';

const STEP_MS = 700;

export function day(iso) {
  return iso ? dateTime(iso).slice(0, 11) : '—';
}

export function durationLabel(hours) {
  if (hours === null || hours === undefined) return null;
  if (hours === 0) return 'day one';
  if (hours < 24) return `${Math.round(hours)} h`;
  return `${(hours / 24).toFixed(1)} days`;
}

/** The projected journey, revealed one step at a time. */
export default function JourneyFlow({ steps, playToken = 0 }) {
  const [shown, setShown] = useState(0);

  useEffect(() => { setShown(0); }, [playToken, steps]);

  useEffect(() => {
    if (shown >= steps.length) return undefined;
    const timer = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 200 : STEP_MS);
    return () => clearTimeout(timer);
  }, [shown, steps]);

  const progress = steps.length ? Math.min(100, (shown / steps.length) * 100) : 0;

  return (
    <>
      <div className="playbar"><span style={{ width: `${progress}%` }} /></div>
      <div className="flow">
        {steps.map((step, index) => (
          <div key={step.stage_id} className={`flow__card${index < shown ? ' flow__card--in' : ''}`}>
            <div className="flow__seq">{index + 1}</div>
            <div className="flow__label">{step.label}</div>
            {step.expected ? (
              <>
                <div className="flow__date">{day(step.expected)}</div>
                <div className="flow__range">{day(step.earliest)} – {day(step.latest)}</div>
                <div className="flow__meta">
                  Day {step.days_from_start.expected} · typical {durationLabel(step.typical_hours)}
                </div>
              </>
            ) : (
              <div className="flow__meta flow__meta--open">{step.basis}</div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
