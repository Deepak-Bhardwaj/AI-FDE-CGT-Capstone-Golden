export function Drawer({ open, eyebrow, title, meta, onClose, children }) {
  return (
    <>
      <div className={`scrim${open ? ' scrim--open' : ''}`} onClick={onClose} />
      <aside className={`drawer${open ? ' drawer--open' : ''}`} aria-hidden={!open}>
        <header className="drawer__head">
          <div style={{ flex: 1, minWidth: 0 }}>
            {eyebrow && <div className="drawer__eyebrow">{eyebrow}</div>}
            <h2 className="drawer__title">{title}</h2>
            {meta && <div style={{ marginTop: 10 }}>{meta}</div>}
          </div>
          <button type="button" className="drawer__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="drawer__body">{open ? children : null}</div>
      </aside>
    </>
  );
}

export function Toast({ toast, onDismiss }) {
  if (!toast) return null;
  return (
    <div
      className={`toast toast--show toast--${toast.tone || 'fail'}`}
      role="status"
      onClick={onDismiss}
    >
      <div className="toast__title">{toast.title}</div>
      <div className="toast__body">{toast.body}</div>
    </div>
  );
}
