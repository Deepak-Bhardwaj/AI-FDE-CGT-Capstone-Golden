/**
 * Single HTTP boundary to the governed API.
 *
 * The browser carries a bearer token this service issued at sign-in. It never sends a role:
 * the server reads the role from the directory entry the token names, so a user cannot widen
 * their own access from the client.
 */

const BASE = import.meta.env.VITE_API_BASE || '';
const STORAGE_KEY = 'cellchain.session';

let token = sessionStorage.getItem(STORAGE_KEY) || '';
let onExpired = () => {};

export function setToken(next) {
  token = next || '';
  if (token) sessionStorage.setItem(STORAGE_KEY, token);
  else sessionStorage.removeItem(STORAGE_KEY);
}

export function getToken() {
  return token;
}

export function onSessionExpired(handler) {
  onExpired = handler;
}

async function request(path, { method = 'GET', body, anonymous = false } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(token && !anonymous ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (response.status === 401 && !anonymous) {
    setToken('');
    onExpired(payload?.detail || 'Your session has ended. Sign in again.');
  }
  return { ok: response.ok, status: response.status, data: payload };
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  anonymous: {
    get: (path) => request(path, { anonymous: true }),
    post: (path, body) => request(path, { method: 'POST', body, anonymous: true }),
  },
};

/** Pull the human-readable reason out of any refusal shape the API can return. */
export function refusalReason(payload) {
  return payload?.reason || payload?.detail || 'Request was refused.';
}
