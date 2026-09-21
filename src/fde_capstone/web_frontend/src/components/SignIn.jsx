import { useEffect, useState } from 'react';
import { api, refusalReason } from '../api/client';
import Logo from './Logo';

export default function SignIn({ onSignedIn, notice }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [accounts, setAccounts] = useState([]);

  useEffect(() => {
    api.anonymous.get('/api/auth/accounts').then((r) => setAccounts(r.data.accounts || []));
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    const { ok, data } = await api.anonymous.post('/api/auth/login', { username, password });
    setBusy(false);
    if (!ok) {
      setError(refusalReason(data));
      return;
    }
    onSignedIn(data);
  };

  return (
    <div className="signin">
      <form className="signin__card" onSubmit={submit}>
        <div className="signin__brand">
          <Logo size={38} />
          <div>
            <div className="signin__name">CellChain</div>
            <div className="signin__tagline">Biotech Control Tower</div>
          </div>
        </div>

        <div className="signin__status">
          <span className="pulse-dot" aria-hidden="true" />
          Control plane live · synthetic estate
        </div>

        <p className="signin__lede">
          Sign in with a directory identity. Role and permitted actions come from the server —
          they cannot be chosen here.
        </p>

        {notice && <div className="callout callout--warn">{notice}</div>}
        {error && <div className="callout callout--fail">{error}</div>}

        <label className="signin__field">
          <span>Username</span>
          <input
            className="field"
            value={username}
            autoComplete="username"
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>

        <label className="signin__field">
          <span>Password</span>
          <input
            className="field"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Authenticating…' : 'Enter control tower'}
        </button>

        {accounts.length > 0 && (
          <div className="signin__directory">
            <div className="signin__directory-head">Demo identities</div>
            <ul>
              {accounts.map((account) => (
                <li key={account.username}>
                  <button type="button" onClick={() => setUsername(account.username)}>
                    {account.username}
                  </button>
                  <span>{account.display_name} — {account.role_label}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </div>
  );
}
