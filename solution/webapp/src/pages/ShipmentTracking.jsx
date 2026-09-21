import { useEffect, useState } from 'react';
import { api } from '../api/client';
import RouteMap from '../components/RouteMap';
import {
  Callout, DataTable, DefinitionList, Loading, Metric, Metrics, Panel, Redactable, SectionTitle, Status, Tag,
} from '../components/ui';
import { dateTime, hours, label } from '../lib/format';

export default function ShipmentTracking({ onOpenShipment }) {
  const [tab, setTab] = useState('fleet');
  const [board, setBoard] = useState(null);
  const [coldChain, setColdChain] = useState(null);

  useEffect(() => {
    api.get('/api/tracking?limit=50&only_issues=true').then((r) => setBoard(r.data));
    api.get('/api/logistics/excursions').then((r) => setColdChain(r.data));
  }, []);

  if (!board) return <Loading />;

  const s = board.summary;
  return (
    <>
      <Metrics>
        <Metric tone="info" label="In transit" value={s.in_transit} caption="Shipments not yet delivered" />
        <Metric tone="critical" label="Service level breached" value={s.sla_breaches} caption={`Of ${board.total} shipments against contracted courier SLAs`} />
        <Metric tone="warn" label="Temperature excursions" value={s.with_excursion_readings} caption="Shipments with readings above −120 °C" />
        <Metric tone="critical" label="Impossible timelines" value={s.impossible_timelines} caption="Arrival recorded before departure" />
        <Metric tone="warn" label="Open escalations" value={s.open_escalations} caption="Raised with the carrier" />
      </Metrics>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'fleet'}
          className={`tabs__item${tab === 'fleet' ? ' tabs__item--active' : ''}`}
          onClick={() => setTab('fleet')}
        >
          Shipments needing attention
          <span className="tabs__count">{board.shown}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'cold'}
          className={`tabs__item${tab === 'cold' ? ' tabs__item--active' : ''}`}
          onClick={() => setTab('cold')}
        >
          Cold chain review
          <span className="tabs__count">{coldChain?.shipments ?? '—'}</span>
        </button>
      </div>

      {tab === 'fleet' && (
        <Panel
          title="Shipments needing attention"
          note={`${board.shown} of ${board.total} shipments shown, issues first. Select a row for the custody chain and telemetry.`}
          flush
        >
          <DataTable
            onRowClick={(row) => onOpenShipment(row.shipment_id)}
            rowClassName={(row) => (row.issue ? 'is-flagged' : '')}
            columns={[
              { key: 'shipment_id', header: 'Shipment', render: (r) => <span className="mono">{r.shipment_id}</span> },
              { key: 'patient_key', header: 'Patient', render: (r) => <span className="mono"><Redactable value={r.patient_key} /></span> },
              { key: 'direction', header: 'Leg', render: (r) => <span className="subtle">{label(r.direction)}</span> },
              { key: 'status', header: 'Status', render: (r) => <Status value={r.status} /> },
              { key: 'courier', header: 'Carrier' },
              { key: 'lane', header: 'Lane', render: (r) => <span className="mono">{r.origin} → {r.destination}</span> },
              {
                key: 'transit_hours', header: 'Transit', align: 'right',
                render: (r) => (r.ordering_valid
                  ? <span className="mono">{r.transit_hours != null ? hours(r.transit_hours) : '—'}</span>
                  : <Status value="CONFLICT">Invalid</Status>),
              },
              {
                key: 'sla_breach', header: 'Service level',
                render: (r) => (r.sla_breach
                  ? <Status value="FAIL">+{(r.transit_hours - r.sla_hours).toFixed(1)}h</Status>
                  : <Status value="PASS">Within SLA</Status>),
              },
              {
                key: 'excursion', header: 'Excursion',
                render: (r) => {
                  if (r.above_threshold) {
                    return <Status value={r.sensor_trustworthy ? 'FAIL' : 'CONFLICT'}>{r.above_threshold} reading(s)</Status>;
                  }
                  return r.flagged ? <Status value="UNKNOWN">Flagged, no data</Status> : <span className="subtle">—</span>;
                },
              },
            ]}
            rows={board.shipments.map((r) => ({ ...r, id: r.shipment_id }))}
          />
        </Panel>
      )}

      {tab === 'cold' && (
        coldChain ? <ColdChainReview data={coldChain} onOpenShipment={onOpenShipment} /> : <Loading />
      )}
    </>
  );
}

function ColdChainReview({ data, onOpenShipment }) {
  const blocked = data.decisions.filter((d) => d.recommendation === 'QA_REVIEW_SENSOR_INTEGRITY').length;

  return (
    <>
      <Callout tone="warn" title={`Evaluated under ${data.sop}`}>
        {data.superseded}. Every shipment below is routed to Quality for disposition — the platform
        never declares material unsuitable.
      </Callout>

      <Metrics>
        <Metric tone="warn" label="Shipments with readings above threshold" value={data.shipments} />
        <Metric tone="critical" label="Sensor integrity in doubt" value={blocked} caption="No above-threshold reading came from a sensor reporting OK" />
        <Metric tone="good" label="Dispositioned automatically" value={0} caption="Reserved for Quality under SOP v7" />
      </Metrics>

      <Panel
        title="Excursion evaluations"
        note="Duration, sensor quality and cumulative profile, per SOP-LOG-007 v7. The superseded v6 point threshold would auto-fail every one of these."
        flush
      >
        <DataTable
          onRowClick={(row) => onOpenShipment(row.shipment_id)}
          columns={[
            { key: 'shipment_id', header: 'Shipment', render: (r) => <span className="mono">{r.subject.shipment_id}</span> },
            { key: 'recommendation', header: 'Recommendation', render: (r) => <Status value="UNKNOWN">{label(r.recommendation)}</Status> },
            {
              key: 'profile', header: 'Excursion profile',
              render: (r) => {
                const p = r.inputs[0]?.value || {};
                return (
                  <span className="muted">
                    {p.above_threshold} above threshold · {p.above_threshold_trusted} from a sensor reporting OK ·
                    max {p.max_temp_c} °C · {p.exposure_window_hours}h window
                  </span>
                );
              },
            },
            { key: 'sop', header: 'Governing rule', render: (r) => <span className="mono">{r.rule.sop_id} {r.rule.sop_version}</span> },
            { key: 'authority', header: 'Disposition authority', render: (r) => <span className="muted">{r.authority_required}</span> },
            { key: 'class', header: 'Action class', render: (r) => <Status value="UNKNOWN">Advisory · {r.action_class}</Status> },
          ]}
          rows={data.decisions.map((d) => ({ ...d, id: d.subject.shipment_id, shipment_id: d.subject.shipment_id }))}
          empty="No shipments have readings above the threshold."
        />
      </Panel>
    </>
  );
}


export function ShipmentDetail({ shipment, onRunAgent }) {
  if (!shipment) return <Loading />;
  const t = shipment;
  const temps = t.telemetry.map((x) => x.temperature_c).filter((v) => v != null);
  const low = Math.min(...temps);
  const high = Math.max(...temps);
  const span = high - low || 1;

  return (
    <>
      {t.anomalies.length > 0 && (
        <>
          <SectionTitle>Anomalies</SectionTitle>
          {t.anomalies.map((a) => (
            <Callout key={a} tone="fail">{a}</Callout>
          ))}
        </>
      )}

      <SectionTitle>Route</SectionTitle>
      <Panel>
        <RouteMap route={t.route} status={label(t.status)} />
      </Panel>

      <SectionTitle>Carrier performance</SectionTitle>
      <Panel>
        <DefinitionList
          wide
          items={[
            ['Carrier', <>{t.sla.courier_name || '—'} <Tag>{t.sla.regions}</Tag></>],
            ['Lane', <>{t.route.origin.city} → {t.route.destination.city} <span className="subtle">({t.route.distance_km.toLocaleString()} km)</span></>],
            ['Dispatched', <span className="mono">{dateTime(t.departed_at)} UTC</span>],
            ['Planned arrival', <span className="mono">{dateTime(t.sla.planned_arrival)} UTC</span>],
            ['Actual arrival', t.arrived_at
              ? <span className="mono">{dateTime(t.arrived_at)} UTC</span>
              : <Status value="UNKNOWN">Not recorded</Status>],
            ['Contracted service level', <span className="mono">{hours(t.sla.sla_hours)}</span>],
            ['Actual transit', t.sla.ordering_valid
              ? <span className="mono">{t.sla.transit_hours != null ? hours(t.sla.transit_hours) : '—'}</span>
              : <Status value="CONFLICT">Arrival precedes departure</Status>],
            ['Outcome', t.sla.sla_breach
              ? <Status value="FAIL">Breached by {hours(t.sla.overrun_hours)}</Status>
              : <Status value="PASS">Within service level</Status>],
          ]}
        />
      </Panel>

      <SectionTitle>Tracking history</SectionTitle>
      <Panel
        note="Times are UTC. Recorded time is when a system learned of the event; a gap between the two means downstream systems were working from stale state."
        flush
      >
        <DataTable
          columns={[
            { key: 'seq', header: '#', align: 'right', render: (r) => <span className="mono subtle">{r.seq}</span> },
            { key: 'title', header: 'Checkpoint', render: (r) => (
              <>
                <div style={{ fontWeight: 600 }}>{r.title}</div>
                {r.note && <div className="subtle" style={{ marginTop: 3 }}>{r.note}</div>}
              </>
            ) },
            { key: 'location', header: 'Location', render: (r) => (
              <>
                <div>{r.city}{r.country ? `, ${r.country}` : ''}</div>
                <div className="mono subtle">{r.lat.toFixed(2)}, {r.lon.toFixed(2)}</div>
              </>
            ) },
            { key: 'occurred_at', header: 'Occurred (UTC)', render: (r) => (
              r.occurred_at ? <span className="mono">{dateTime(r.occurred_at)}</span> : <span className="subtle">—</span>
            ) },
            { key: 'recorded_at', header: 'Recorded (UTC)', render: (r) => (
              r.recorded_at ? <span className="mono">{dateTime(r.recorded_at)}</span> : <span className="subtle">—</span>
            ) },
            { key: 'ingest_lag_hours', header: 'Ingest lag', align: 'right', render: (r) => (
              r.ingest_lag_hours == null ? <span className="subtle">—</span>
                : <span className="mono" style={r.ingest_lag_hours > 6 ? { color: 'var(--unknown)' } : undefined}>
                    {hours(r.ingest_lag_hours)}
                  </span>
            ) },
            { key: 'elapsed_hours', header: 'Since dispatch', align: 'right', render: (r) => (
              r.elapsed_hours == null ? <span className="subtle">—</span> : <span className="mono">{hours(r.elapsed_hours)}</span>
            ) },
            { key: 'source', header: 'Source', render: (r) => <span className="mono subtle">{r.source}</span> },
            { key: 'status', header: 'Status', render: (r) => <Status value={r.status} /> },
          ]}
          rows={t.checkpoints.map((c) => ({ ...c, id: c.seq }))}
        />
      </Panel>

      <SectionTitle>Cryogenic telemetry</SectionTitle>
      <Panel note={`${t.telemetry.length} readings · threshold −120 °C · observed range ${low.toFixed(1)} to ${high.toFixed(1)} °C`}>
        <div className="chart">
          {t.telemetry.map((r, i) => {
            const height = r.temperature_c == null ? 3 : ((r.temperature_c - low) / span) * 96 + 8;
            const modifier = r.above_threshold ? ' chart__bar--hot' : r.quality !== 'OK' ? ' chart__bar--degraded' : '';
            return (
              <div
                key={i}
                className={`chart__bar${modifier}`}
                style={{ height }}
                title={`${r.timestamp} · ${r.temperature_c} °C · sensor ${label(r.quality)}`}
              />
            );
          })}
        </div>
        <div className="chart__legend">
          <span className="chart__key"><span className="chart__swatch" style={{ background: 'var(--info)' }} /> Nominal</span>
          <span className="chart__key"><span className="chart__swatch" style={{ background: 'var(--unknown)' }} /> Degraded sensor</span>
          <span className="chart__key"><span className="chart__swatch" style={{ background: 'var(--fail)' }} /> Above −120 °C</span>
        </div>
        <div style={{ marginTop: 18 }}>
          <DefinitionList
            wide
            items={[
              ['Readings above threshold', <span className="mono">{t.excursion_profile.above_threshold}</span>],
              ['…from a sensor reporting OK', <span className="mono">{t.excursion_profile.above_threshold_trusted}</span>],
              ['Exposure window', <span className="mono">{hours(t.excursion_profile.exposure_window_hours)}</span>],
              ['Maximum temperature', <span className="mono">{t.excursion_profile.max_temp_c ?? '—'} °C</span>],
              ['Flagged by logistics', <span className="mono">{String(t.excursion_profile.flagged_by_logistics)}</span>],
            ]}
          />
        </div>
      </Panel>

      <SectionTitle>Disposition recommendation</SectionTitle>
      <Callout tone="warn" title={label(t.excursion_decision.recommendation)}>
        <div className="row" style={{ marginBottom: 8 }}>
          <Tag>{t.excursion_decision.rule.sop_id} {t.excursion_decision.rule.sop_version}</Tag>
          <Tag>Advisory (Class {t.excursion_decision.action_class})</Tag>
        </div>
        <div>{t.excursion_decision.rationale}</div>
        <div style={{ marginTop: 8 }} className="muted">
          Authority: {t.excursion_decision.authority_required}. The platform never dispositions material.
        </div>
      </Callout>

      {t.escalations.length > 0 && (
        <>
          <SectionTitle>Carrier escalations</SectionTitle>
          <Panel flush>
            <DataTable
              columns={[
                { key: 'issue', header: 'Issue', render: (r) => label(r.issue) },
                { key: 'status', header: 'Status', render: (r) => <Status value={r.status} /> },
                { key: 'owner', header: 'Owner', render: (r) => (r.owner ? r.owner : <Status value="FAIL">Unassigned</Status>) },
              ]}
              rows={t.escalations.map((e, i) => ({ ...e, id: i }))}
            />
          </Panel>
        </>
      )}

      <div className="row" style={{ marginTop: 20 }}>
        <button type="button" className="btn btn--outline" onClick={() => onRunAgent('AG-ROUTE', t.patient_key)}>
          Ask the route advisor
        </button>
      </div>
    </>
  );
}
