import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { DataTable, Loading, Panel, Redactable, Status } from '../components/ui';
import { label, percent } from '../lib/format';

const FILTERS = [
  { value: '', text: 'All', tone: 'all' },
  { value: 'BLOCKED', text: 'Blocked', tone: 'fail' },
  { value: 'CONFLICTED', text: 'Conflicted', tone: 'conflict' },
  { value: 'NEEDS_EVIDENCE', text: 'Needs evidence', tone: 'unknown' },
  { value: 'READY', text: 'Ready', tone: 'pass' },
];

function Count({ value, tone }) {
  if (!value) return <span className="subtle">—</span>;
  return <span className={`countpill countpill--${tone}`}>{value}</span>;
}

export default function ReadinessReview({ onOpenReadiness }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [payload, setPayload] = useState(null);

  const load = useCallback(() => {
    setPayload(null);
    api
      .get(`/api/journeys?q=${encodeURIComponent(query)}&readiness=${filter}&limit=60`)
      .then((r) => setPayload(r.data));
  }, [query, filter]);

  useEffect(() => {
    const timer = setTimeout(load, 220);
    return () => clearTimeout(timer);
  }, [load]);

  const rows = payload?.journeys || [];
  const attention = rows.filter((r) => r.failed || r.conflicts).length;

  return (
    <>
      <div className="filterbar">
        <div className="inputwrap">
          <span className="inputwrap__icon" aria-hidden="true">⌕</span>
          <input
            className="field inputwrap__field"
            placeholder="Search patients by identifier or name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search patients"
          />
          {query && (
            <button type="button" className="inputwrap__clear" onClick={() => setQuery('')} aria-label="Clear search">✕</button>
          )}
        </div>

        <div className="segmented" role="group" aria-label="Filter by readiness">
          {FILTERS.map((f) => (
            <button
              key={f.value || 'all'}
              type="button"
              className={`segmented__item segmented__item--${f.tone}${filter === f.value ? ' segmented__item--on' : ''}`}
              onClick={() => setFilter(f.value)}
              aria-pressed={filter === f.value}
            >
              {f.text}
            </button>
          ))}
        </div>

        {payload && (
          <div className="filterbar__meta">
            <strong>{rows.length}</strong> shown
            {attention > 0 && <span className="filterbar__flag">{attention} need attention</span>}
          </div>
        )}
      </div>

      {!payload ? (
        <Loading />
      ) : (
        <Panel
          title="Patient readiness"
          note={
            payload.redacted_fields?.length
              ? `Fields withheld for this role: ${payload.redacted_fields.join(', ')}`
              : 'Select a row to inspect the ten readiness gates and their evidence.'
          }
          flush
        >
          <DataTable
            onRowClick={(row) => onOpenReadiness(row.patient_key)}
            rowClassName={(row) => (row.conflicts > 0 ? 'is-flagged' : '')}
            columns={[
              {
                key: 'patient_key',
                header: 'Patient',
                render: (r) => (
                  <div className="idcell">
                    <span className="idcell__name">
                      <Redactable value={r.patient_name} fallback="Name not recorded" />
                    </span>
                    <button
                      type="button"
                      className="idcell__link mono"
                      title={`Open patient information for ${r.patient_key}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenReadiness(r.patient_key);
                      }}
                    >
                      <Redactable value={r.patient_key} />
                    </button>
                  </div>
                ),
              },
              { key: 'readiness', header: 'Governed readiness', render: (r) => <Status value={r.readiness} /> },
              { key: 'legacy_status', header: 'Legacy status', render: (r) => <span className="muted">{label(r.legacy_status)}</span> },
              {
                key: 'confidence',
                header: 'Gates passed',
                width: 150,
                render: (r) => (
                  <div className="gauge">
                    <div className="gauge__track">
                      <span
                        className={`gauge__fill gauge__fill--${r.confidence >= 0.9 ? 'pass' : r.confidence >= 0.6 ? 'warn' : 'fail'}`}
                        style={{ width: `${Math.round((r.confidence || 0) * 100)}%` }}
                      />
                    </div>
                    <span className="gauge__value">{percent(r.confidence)}</span>
                  </div>
                ),
              },
              { key: 'failed', header: 'Failed', align: 'right', render: (r) => <Count value={r.failed} tone="fail" /> },
              { key: 'conflicts', header: 'Conflicts', align: 'right', render: (r) => <Count value={r.conflicts} tone="conflict" /> },
              { key: 'unknown', header: 'Missing', align: 'right', render: (r) => <Count value={r.unknown} tone="unknown" /> },
              { key: 'center_id', header: 'Treatment centre', render: (r) => <span className="mono">{r.center_id}</span> },
              { key: 'authority', header: 'Authority required', render: (r) => <span className="ownercell">{r.authority}</span> },
            ]}
            rows={rows.map((j) => ({ ...j, id: j.patient_key }))}
            empty="No journeys match this filter."
          />
        </Panel>
      )}
    </>
  );
}
