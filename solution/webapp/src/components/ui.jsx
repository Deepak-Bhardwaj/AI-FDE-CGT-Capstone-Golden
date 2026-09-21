import { useMemo, useState } from 'react';
import { toneFor, label, isRedacted, REDACTED } from '../lib/format';

export function Status({ value, children, dot = false }) {
  const tone = toneFor(value);
  return (
    <span className={`status status--${tone}${dot ? ' status--dot' : ''}`}>
      {children ?? label(value)}
    </span>
  );
}

export function Tag({ children }) {
  return <span className="tag">{children}</span>;
}

export function Redactable({ value, fallback = '—' }) {
  if (isRedacted(value)) {
    return <span className="subtle" title="Withheld: not necessary for this role">{REDACTED}</span>;
  }
  return <>{value ?? fallback}</>;
}

export function Panel({ title, note, actions, children, flush = false }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel__head">
          <div>
            {title && <h2 className="panel__title">{title}</h2>}
            {note && <p className="panel__note">{note}</p>}
          </div>
          <div className="panel__spacer" />
          {actions}
        </header>
      )}
      <div className={`panel__body${flush ? ' panel__body--flush' : ''}`}>{children}</div>
    </section>
  );
}

export function Metric({ label: text, value, caption, tone = 'default' }) {
  return (
    <div className={`metric${tone === 'default' ? '' : ` metric--${tone}`}`}>
      <div className="metric__label">{text}</div>
      <div className="metric__value">{value}</div>
      {caption && <div className="metric__caption">{caption}</div>}
    </div>
  );
}

export function Metrics({ children }) {
  return <div className="metrics">{children}</div>;
}

export function Callout({ tone = 'info', title, children }) {
  return (
    <div className={`callout callout--${tone}`}>
      {title && <div className="callout__title">{title}</div>}
      {children}
    </div>
  );
}

export function DataTable({
  columns, rows, onRowClick, rowClassName, empty = 'Nothing to show.', pageSize = 25,
}) {
  const [sort, setSort] = useState({ key: null, dir: 'asc' });
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort.key) return rows || [];
    const factor = sort.dir === 'asc' ? 1 : -1;
    return [...(rows || [])].sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * factor;
      return String(x).localeCompare(String(y), undefined, { numeric: true }) * factor;
    });
  }, [rows, sort]);

  const pages = Math.ceil(sorted.length / pageSize) || 1;
  const current = Math.min(page, pages - 1);
  const slice = sorted.slice(current * pageSize, current * pageSize + pageSize);

  if (!rows?.length) return <div className="empty">{empty}</div>;

  const toggleSort = (key) => {
    setPage(0);
    setSort((s) => (s.key === key
      ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'asc' }));
  };

  return (
    <>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              {columns.map((col) => {
                const sortable = col.sortable !== false;
                const active = sort.key === col.key;
                return (
                  <th
                    key={col.key}
                    style={col.width ? { width: col.width } : undefined}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        className={`th-sort${active ? ' th-sort--on' : ''}`}
                        onClick={() => toggleSort(col.key)}
                      >
                        {col.header}
                        <span className="th-sort__arrow" aria-hidden="true">
                          {active ? (sort.dir === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </button>
                    ) : col.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {slice.map((row, index) => (
              <tr
                key={row.id ?? index}
                className={[onRowClick ? 'is-clickable' : '', rowClassName?.(row) || '']
                  .filter(Boolean)
                  .join(' ')}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className={col.align === 'right' ? 'num' : undefined}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="pager">
          <span className="pager__info">
            {current * pageSize + 1}–{Math.min((current + 1) * pageSize, sorted.length)} of {sorted.length}
          </span>
          <div className="pager__controls">
            <button
              type="button" className="pager__btn"
              onClick={() => setPage(current - 1)} disabled={current === 0}
              aria-label="Previous page"
            >‹</button>
            <span className="pager__page">Page {current + 1} of {pages}</span>
            <button
              type="button" className="pager__btn"
              onClick={() => setPage(current + 1)} disabled={current >= pages - 1}
              aria-label="Next page"
            >›</button>
          </div>
        </div>
      )}
    </>
  );
}

export function DefinitionList({ items, wide = false }) {
  return (
    <dl className={`dl${wide ? ' dl--wide' : ''}`}>
      {items.map(([term, value]) => (
        <div key={term} style={{ display: 'contents' }}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SectionTitle({ children }) {
  return <h3 className="section-title">{children}</h3>;
}

export function Loading({ text = 'Loading…' }) {
  return (
    <div className="skeleton-page" role="status" aria-live="polite" aria-label={text}>
      <div className="skeleton-row">
        <span className="sk sk--card" /><span className="sk sk--card" />
        <span className="sk sk--card" /><span className="sk sk--card" />
      </div>
      <div className="sk sk--panel">
        <span className="sk sk--line sk--w40" />
        <span className="sk sk--line sk--w80" />
        <span className="sk sk--line sk--w60" />
        <span className="sk sk--line sk--w70" />
        <span className="sk sk--line sk--w50" />
      </div>
      <span className="visually-hidden">{text}</span>
    </div>
  );
}

export function Empty({ text }) {
  return <div className="empty">{text}</div>;
}
