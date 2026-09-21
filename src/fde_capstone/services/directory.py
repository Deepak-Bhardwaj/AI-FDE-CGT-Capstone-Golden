"""Who the people are, and how a session proves it.

Separation of duties: a person's role is an attribute of their directory entry, granted by an
administrator. The browser never sends a role and no signed-in user can change their own; the
server derives the role from the session token on every request.

In a real deployment this module is replaced by the enterprise identity provider (OIDC, SCIM
group membership). The contract the rest of the service depends on stays the same: authenticate
a credential, return a directory entry, and carry it in a signed, expiring session token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

PBKDF2_ITERATIONS = 240_000
SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

# Token signing key. Generated per process unless one is supplied, so no key is ever committed
# and sessions never outlive a restart.
_SIGNING_KEY = (os.environ.get("CELLCHAIN_SESSION_SECRET") or secrets.token_hex(32)).encode()

# Synthetic environment only: every seeded account shares this password so the reference
# implementation can be demonstrated offline. A real directory never holds a shared credential.
DEMO_PASSWORD = os.environ.get("CELLCHAIN_DEMO_PASSWORD", "demo")


class InvalidSession(Exception):
    """Raised when a token is missing, malformed, tampered with or expired."""


class AuthenticationError(Exception):
    """Raised when credentials are wrong or the account is temporarily locked."""


@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    job_title: str
    role: str
    salt: bytes
    password_hash: bytes

    @property
    def identity(self) -> str:
        return f"{self.username}@gds.ey.com"

    def as_dict(self) -> dict:
        return {"username": self.username, "display_name": self.display_name,
                "job_title": self.job_title, "role": self.role, "identity": self.identity}


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)


def _seed(username: str, display_name: str, job_title: str, role: str) -> User:
    salt = secrets.token_bytes(16)
    return User(username, display_name, job_title, role, salt, _hash(DEMO_PASSWORD, salt))


# One named person per duty. No account holds two roles, and the AI service identity is not a
# person at all, so it cannot sign in here. Audit is held by a different human from the
# qualified persons, because separate accounts for one person are not separation of duties.
# Two qualified persons exist because release is a two-person action: one signs, a different
# one countersigns. A single quality account would make dual control unsatisfiable.
USERS: dict[str, User] = {
    u.username: u for u in [
        _seed("deepak.bhardwaj", "Deepak Bhardwaj",
              "Operations coordinator, cell therapy desk", "ops_coordinator"),
        _seed("parvateesam.naidu", "Parvateesam Naidu",
              "Chain-of-identity adjudicator, Patient Safety", "identity_adjudicator"),
        _seed("rohit.menon", "Rohit Menon",
              "Chain-of-identity adjudicator, Patient Safety (second approver)",
              "identity_adjudicator"),
        _seed("sandeep.raj", "Sandeep Raj", "Qualified person, Quality Assurance",
              "quality_reviewer"),
        _seed("anita.krishnan", "Anita Krishnan",
              "Qualified person, Quality Assurance (second approver)", "quality_reviewer"),
        _seed("sharat.p.surya", "Sharat P Surya", "Manufacturing planner, slot and capacity control",
              "manufacturing_planner"),
        _seed("mrinal.kanti.paul", "Mrinal Kanti Paul", "Logistics coordinator, cryogenic transport",
              "logistics_coordinator"),
        _seed("nandita.rao", "Nandita Rao", "Internal auditor, Quality Systems", "auditor"),
    ]
}

_failures: dict[str, list[float]] = {}
_revoked: set[str] = set()


def directory_listing() -> list[dict]:
    """Accounts that exist, without any credential material."""
    return [u.as_dict() for u in USERS.values()]


def authenticate(username: str, password: str) -> User:
    """Verify a credential. The failure message never says which half was wrong."""
    username = (username or "").strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < LOCKOUT_SECONDS]
    _failures[username] = recent
    if len(recent) >= MAX_FAILED_ATTEMPTS:
        raise AuthenticationError(
            "too many failed attempts for this account; try again in a minute")

    user = USERS.get(username)
    # Hash even when the account is unknown, so a missing account and a wrong password cost
    # the same amount of time.
    reference = user.salt if user else b"\x00" * 16
    candidate = _hash(password or "", reference)
    if user is None or not hmac.compare_digest(candidate, user.password_hash):
        _failures.setdefault(username, []).append(now)
        raise AuthenticationError("username or password is incorrect")

    _failures.pop(username, None)
    return user


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(user: User) -> dict:
    """Sign a short-lived bearer token. The role is not in the client's gift."""
    issued = int(time.time())
    payload = {"sub": user.username, "iat": issued, "exp": issued + SESSION_TTL_SECONDS,
               "jti": secrets.token_urlsafe(12)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_SIGNING_KEY, body.encode(), hashlib.sha256).digest())
    return {"token": f"{body}.{signature}", "expires_at": payload["exp"]}


def resolve(token: str | None) -> User:
    """Validate a bearer token and return the directory entry it names."""
    if not token or "." not in token:
        raise InvalidSession("sign in to continue")
    body, _, signature = token.partition(".")
    expected = _b64(hmac.new(_SIGNING_KEY, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise InvalidSession("session token is not valid")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidSession("session token is not valid") from exc
    if payload.get("jti") in _revoked:
        raise InvalidSession("this session has been signed out")
    if int(payload.get("exp", 0)) < time.time():
        raise InvalidSession("session has expired; sign in again")
    user = USERS.get(payload.get("sub", ""))
    if user is None:
        raise InvalidSession("this account no longer exists")
    return user


def revoke(token: str | None) -> None:
    if not token or "." not in token:
        return
    try:
        payload = json.loads(_unb64(token.partition(".")[0]))
    except (ValueError, json.JSONDecodeError):
        return
    if jti := payload.get("jti"):
        _revoked.add(jti)
