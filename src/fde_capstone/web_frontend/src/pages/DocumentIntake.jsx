import { useCallback, useEffect, useRef, useState } from 'react';
import { api, refusalReason } from '../api/client';
import { Callout, DataTable, Loading, Metric, Metrics, Panel, Status } from '../components/ui';
import { holdsAuthority } from '../lib/authority';
import { label } from '../lib/format';

export default function DocumentIntake({ notify, roleName }) {
  const [data, setData] = useState(null);
  const [samples, setSamples] = useState([]);
  const [lastUpload, setLastUpload] = useState(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  const load = useCallback(() => {
    api.get('/api/intake').then((r) => setData(r.data));
  }, []);

  useEffect(() => {
    load();
    api.get('/api/intake/samples').then((r) => setSamples(r.data.samples || []));
  }, [load]);

  const upload = async (filename, content) => {
    const { ok, data: payload } = await api.post('/api/intake/upload', { filename, content });
    if (!ok) {
      notify({ tone: 'fail', title: 'Upload rejected', body: refusalReason(payload) });
      return;
    }
    setLastUpload(payload.record);
    notify({
      tone: 'warn',
      title: 'Document received',
      body: `${payload.record.proposals.length} proposal(s) queued for review. Nothing was applied.`,
    });
    load();
  };

  const readFile = (file) => {
    const reader = new FileReader();
    reader.onload = () => upload(file.name, String(reader.result));
    reader.readAsText(file);
  };

  const decide = async (proposal, decision) => {
    const reason = decision === 'REJECTED'
      ? window.prompt('Reason for rejection:') || ''
      : 'Confirmed after review';
    const { ok, data: payload } = await api.post(
      `/api/intake/proposals/${proposal.proposal_id}/decide`,
      { decision, reason },
    );
    if (!ok) {
      notify({ tone: 'fail', title: 'Decision refused', body: refusalReason(payload) });
      return;
    }
    notify({
      tone: decision === 'CONFIRMED' ? 'pass' : 'warn',
      title: label(decision),
      body: `Recorded against ${payload.proposal.decided_by}.`,
    });
    load();
  };

  if (!data) return <Loading />;

  return (
    <>
      <Metrics>
        <Metric tone="info" label="Documents received" value={data.totals.uploads} />
        <Metric tone="info" label="Proposals raised" value={data.totals.proposals} />
        <Metric tone="warn" label="Awaiting a decision" value={data.totals.pending} caption="Each requires a named authority" />
        <Metric tone="good" label="Applied automatically" value={data.totals.auto_applied} caption="Structurally impossible" />
      </Metrics>

      <Panel
        title="Upload a document or report"
        note="Correspondence (.eml, .txt), QC reports, courier manifests and chain-of-identity evidence. Parsed, classified and converted into proposals — never applied."
      >
        <div
          className={`dropzone${dragging ? ' dropzone--over' : ''}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) readFile(file);
          }}
        >
          <div className="dropzone__icon">⇪</div>
          <div className="dropzone__title">Drop a file here, or select one</div>
          <div className="dropzone__hint">Processed locally. Nothing is transmitted outside this machine.</div>
        </div>
        <input
          ref={fileInput}
          type="file"
          style={{ display: 'none' }}
          onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])}
        />

        {samples.length > 0 && (
          <>
            <p className="panel__note" style={{ marginTop: 18 }}>Or try a prepared example:</p>
            <div className="row">
              {samples.map((sample, index) => (
                <button
                  key={index}
                  type="button"
                  className="btn btn--outline btn--sm"
                  onClick={() => upload(sample.filename, sample.content)}
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </>
        )}

        {lastUpload && (
          <div style={{ marginTop: 18 }}>
            <Callout tone={lastUpload.injection_detected ? 'fail' : 'warn'} title={lastUpload.filename}>
              <div className="row" style={{ marginBottom: 8 }}>
                <Status value="UNTRUSTED" />
                <Status value="INFO">{label(lastUpload.kind)}</Status>
                <Status value="PASS">Applied automatically: 0</Status>
                {lastUpload.injection_detected && <Status value="FAIL">Instruction patterns detected</Status>}
              </div>
              <div>{lastUpload.proposals.length} proposal(s) raised, each awaiting a named human.</div>
              {lastUpload.notes.map((note) => (
                <div key={note} className="muted" style={{ marginTop: 6, fontSize: 14.5 }}>· {note}</div>
              ))}
            </Callout>
          </div>
        )}
      </Panel>

      <Panel
        title="Proposals awaiting a decision"
        note="Each proposal names the authority that must decide. Any other role is refused."
        flush
      >
        <DataTable
          columns={[
            { key: 'kind', header: 'Type', render: (r) => <Status value="CONFLICT">{label(r.kind)}</Status> },
            { key: 'subject', header: 'Patient', render: (r) => <span className="mono">{r.subject || '—'}</span> },
            { key: 'detail', header: 'Finding', render: (r) => <span className="muted">{r.detail}</span> },
            { key: 'authority', header: 'Decision authority' },
            {
              key: 'corroborated', header: 'Corroborated',
              render: (r) => <Status value={r.corroborated ? 'PASS' : 'UNKNOWN'}>{r.corroborated ? 'Yes' : 'No'}</Status>,
            },
            {
              key: 'actions', header: '',
              render: (r) => (holdsAuthority(r.authority, roleName) ? (
                <div className="row" style={{ flexWrap: 'nowrap' }}>
                  <button type="button" className="btn btn--primary btn--sm" onClick={() => decide(r, 'CONFIRMED')}>Confirm</button>
                  <button type="button" className="btn btn--outline btn--sm" onClick={() => decide(r, 'REJECTED')}>Reject</button>
                </div>
              ) : (
                <span className="subtle">Awaits {r.authority}</span>
              )),
            },
          ]}
          rows={data.pending.map((p) => ({ ...p, id: p.proposal_id }))}
          empty="Nothing pending. Upload a document to generate proposals."
        />
      </Panel>

      <Panel title="Intake history" flush>
        <DataTable
          columns={[
            { key: 'filename', header: 'File', render: (r) => <span className="mono">{r.filename}</span> },
            { key: 'kind', header: 'Classified as', render: (r) => label(r.kind) },
            { key: 'trust', header: 'Trust', render: (r) => <Status value="UNTRUSTED" /> },
            { key: 'injection_detected', header: 'Security', render: (r) => (r.injection_detected ? <Status value="FAIL">Patterns detected</Status> : <span className="subtle">Clean</span>) },
            { key: 'proposals', header: 'Proposals', align: 'right', render: (r) => <span className="mono">{r.proposals.length}</span> },
            { key: 'sha256', header: 'Checksum', render: (r) => <span className="mono subtle">{r.sha256.slice(0, 14)}</span> },
            { key: 'uploaded_by', header: 'Received from', render: (r) => <span className="mono">{r.uploaded_by}</span> },
          ]}
          rows={data.records.map((r) => ({ ...r, id: r.intake_id }))}
          empty="No documents received yet."
        />
      </Panel>
    </>
  );
}
