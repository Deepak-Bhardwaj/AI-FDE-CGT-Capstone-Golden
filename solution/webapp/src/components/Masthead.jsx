import Logo from './Logo';

export default function Masthead({ user, role, onSignOut, onToggleNav, environment }) {
  const initials = (user?.display_name || '??')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <header className="masthead">
      <div className="masthead__inner">
        <button type="button" className="masthead__toggle" onClick={onToggleNav} aria-label="Toggle navigation">
          ☰
        </button>
        <div className="masthead__brand">
          <Logo size={30} />
          <span className="masthead__name">CellChain</span>
          <span className="masthead__tagline">Patient-to-Batch Orchestration Control Tower</span>
        </div>

        <div className="masthead__spacer" />

        <div className="masthead__meta">
          <span className="env-tag" title="Synthetic data. Deterministic control plane; no model configured.">
            {environment}
          </span>

          <div className="whoami">
            <span className="whoami__name">{user?.display_name}</span>
            <span className="whoami__role" title={`${user?.job_title || ''} — ${role?.description || ''}`}>
              {role?.label}
            </span>
          </div>

          <div className="avatar" title={user?.identity || ''}>{initials}</div>

          <button type="button" className="btn btn--ghost btn--sm" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
