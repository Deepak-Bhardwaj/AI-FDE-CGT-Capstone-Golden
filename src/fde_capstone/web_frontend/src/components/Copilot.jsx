import { useEffect, useRef, useState } from 'react';
import { api, refusalReason } from '../api/client';
import { Status } from './ui';
import { percent } from '../lib/format';

// Which assistant answers which intent, and where each one makes sense.
const INTENTS = [
  { id: 'AG-EXPLAIN', label: 'Why is this patient blocked?', needsSubject: true, glyph: '◈' },
  { id: 'AG-JOURNEY', label: 'When will this therapy be ready?', needsSubject: true, glyph: '◷' },
  { id: 'AG-FORECAST', label: 'Forecast the QA release window', needsSubject: true, glyph: '◔' },
  { id: 'AG-TRIAGE', label: 'What should I work on first?', needsSubject: false, glyph: '▲' },
  { id: 'AG-ROUTE', label: 'Review the logistics route', needsSubject: true, glyph: '➤' },
];

const GREETING = {
  role: 'assistant',
  text: 'Ask about a patient, or pick a suggestion. I explain and forecast — every answer cites '
    + 'its evidence, and I can never change a gate or act on your behalf.',
};

export default function Copilot({ patientKey, pageTitle, roleName }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [allowed, setAllowed] = useState(null);
  const endRef = useRef(null);

  // Only offer assistants this role is actually a permitted caller of.
  useEffect(() => {
    api.get('/api/agents').then(({ ok, data }) => {
      if (!ok) return;
      setAllowed((data.agents || [])
        .filter((a) => a.contract.allowed_callers.includes(roleName))
        .map((a) => a.agent_id));
    });
  }, [roleName]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, open]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
      if (e.key === '/' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setOpen((v) => !v); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const suggestions = INTENTS.filter((i) => !allowed || allowed.includes(i.id));

  const ask = async (intent, subject) => {
    const target = intent.needsSubject ? (subject || patientKey) : '';
    setMessages((m) => [...m, { role: 'user', text: intent.label + (target ? ` — ${target}` : '') }]);
    setBusy(true);
    const { ok, data } = await api.post(`/api/agents/${intent.id}/invoke`, { subject: target });
    setBusy(false);
    setMessages((m) => [...m, ok
      ? {
        role: 'assistant',
        text: data.result.summary,
        agent: intent.id,
        glyph: intent.glyph,
        confidence: data.result.confidence,
        uncertainty: data.result.uncertainty,
        authority: data.result.required_authority,
      }
      : { role: 'assistant', text: refusalReason(data), refused: true }]);
  };

  const submit = (event) => {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput('');
    const key = text.match(/P-\d{5}/i)?.[0]?.toUpperCase();
    const lower = text.toLowerCase();
    const intent = /when|ready|date|timeline|forecast/.test(lower)
      ? INTENTS[1]
      : /prioriti|first|triage|queue/.test(lower)
        ? INTENTS[3]
        : /route|courier|shipment|logistics/.test(lower)
          ? INTENTS[4]
          : INTENTS[0];
    ask({ ...intent, label: text }, key);
  };

  return (
    <>
      <button
        type="button"
        className={`ai-launcher${open ? ' ai-launcher--open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-label="Open the CellChain assistant"
        title="Ask CellChain — Ctrl/⌘ + /"
      >
        <span className="ai-launcher__spark">✦</span>
        <span className="ai-launcher__text">Ask CellChain</span>
      </button>

      <aside className={`copilot${open ? ' copilot--open' : ''}`} aria-hidden={!open}>
        <header className="copilot__head">
          <div className="copilot__orb" aria-hidden="true"><i /></div>
          <div>
            <div className="copilot__title">CellChain assistant</div>
            <div className="copilot__ctx">{pageTitle}{patientKey ? ` · ${patientKey}` : ''}</div>
          </div>
          <button type="button" className="copilot__close" onClick={() => setOpen(false)} aria-label="Close">✕</button>
        </header>

        <div className="copilot__thread">
          {messages.map((m, i) => (
            <div key={i} className={`bubble bubble--${m.role}${m.refused ? ' bubble--refused' : ''}`}>
              {m.role === 'assistant' && <span className="bubble__glyph">{m.glyph || '✦'}</span>}
              <div className="bubble__body">
                <div>{m.text}</div>
                {m.confidence !== undefined && (
                  <>
                    <div className="ai-confidence"><span style={{ width: `${Math.round(m.confidence * 100)}%` }} /></div>
                    <div className="bubble__meta">
                      <span className="mono">{m.agent}</span>
                      <Status value="UNKNOWN">Advisory</Status>
                      <span>Confidence {percent(m.confidence)}</span>
                      <span>Decides: {m.authority}</span>
                    </div>
                    <div className="bubble__caveat">{m.uncertainty}</div>
                  </>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="bubble bubble--assistant">
              <span className="bubble__glyph">✦</span>
              <div className="bubble__body"><span className="typing"><i /><i /><i /></span></div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="copilot__suggest">
          {suggestions.map((s) => (
            <button key={s.id} type="button" className="chip" onClick={() => ask(s)} disabled={busy}>
              <span aria-hidden="true">{s.glyph}</span>{s.label}
            </button>
          ))}
        </div>

        <form className="copilot__compose" onSubmit={submit}>
          <input
            className="copilot__input"
            placeholder={`Ask about ${patientKey || 'a patient'}…`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Ask the assistant"
            disabled={busy}
          />
          <button type="submit" className="copilot__send" disabled={busy || !input.trim()} aria-label="Send">↑</button>
        </form>
        <div className="copilot__foot">
          Advisory only · never applies a change · every answer is logged with its evidence
        </div>
      </aside>
    </>
  );
}
