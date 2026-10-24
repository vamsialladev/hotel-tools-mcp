"""Demo authentication: an API key maps to a role, a hotel group (tenant) and a subject.

Only SHA-256 hashes of keys are stored (in a git-ignored keys file made by scripts/make_keys.py). The MCP client passes
its key in the HOTEL_MCP_API_KEY environment variable of the server process. docs/AUTH.md explains how OAuth / SSO
would replace this.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

ROLES = ("guest", "front_desk", "manager", "auditor")


class AuthError(Exception):
    """No key, an unknown key, or a malformed keys file. The message never contains the key."""


@dataclass(frozen=True)
class Principal:
    role: str
    hotel_group_id: str
    subject: str  # guest: their email; staff: a staff id

    def __post_init__(self):
        if self.role not in ROLES:
            raise AuthError(f"unknown role {self.role!r}")


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_key(role: str) -> str:
    return f"hmcp_{role}_{secrets.token_urlsafe(24)}"


def load_keys(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuthError(f"keys file not found: {path}. Run python scripts/make_keys.py") from exc
    except ValueError as exc:
        raise AuthError("keys file is not valid JSON") from exc
    if not isinstance(data, dict):
        raise AuthError("keys file must map key hashes to principals")
    return data


def authenticate(key: str | None, keys: dict) -> Principal:
    if not key:
        raise AuthError("no API key: set HOTEL_MCP_API_KEY in the MCP client's config")
    digest = key_hash(key)
    match = next((v for h, v in keys.items() if hmac.compare_digest(h, digest)), None)
    if match is None:
        raise AuthError("unknown API key")
    return Principal(match["role"], match["hotel_group_id"], match["subject"])


def add_key(keys: dict, role: str, hotel_group_id: str, subject: str) -> str:
    """Creates a key, stores its hash in `keys`, returns the key (shown once, never stored)."""
    key = new_key(role)
    Principal(role, hotel_group_id, subject)  # validates the role
    keys[key_hash(key)] = {"role": role, "hotel_group_id": hotel_group_id, "subject": subject}
    return key
