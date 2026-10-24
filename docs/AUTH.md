# Authentication and authorization

## What the demo does

- `scripts/make_keys.py` creates one random key per role (`hmcp_<role>_<random>`) and stores only SHA-256 hashes in
  `.hotel-mcp/keys.json`, mapped to a role, a hotel group and a subject (a guest's email or a staff id).
- The MCP client starts the server with `HOTEL_MCP_API_KEY` in its environment. The server hashes it, finds the
  principal, and refuses to start for an unknown key (the error never repeats the key).
- One process serves one key, so the role is fixed for the session: the server registers only that role's tools,
  and `tools.call()` checks the role again on every call.
- Re-running `make_keys.py` rotates every key at once.

This is enough to show role and tenant boundaries. It is not how a client should run it in production: keys are
long-lived, shared by whoever has the file, and not tied to a person.

## How OAuth / SSO replaces it

1. **Transport:** run the server over streamable HTTP behind the client's gateway instead of stdio. The MCP
   specification defines authorization for HTTP transports with OAuth 2.1; the Python SDK's `MCPServer` accepts a
   `token_verifier` and `auth` settings for this.
2. **Identity provider:** the hotel group's IdP (Entra ID, Okta, Google Workspace) issues short-lived access tokens
   after SSO sign-in. Guests would sign in through the guest app's own flow, not the staff IdP.
3. **Claims → principal:** the token's `sub` is the subject; a group claim maps to the role (`hotel-front-desk` →
   `front_desk`); a tenant claim (or the IdP tenant itself) maps to `hotel_group_id`. `auth.authenticate` becomes
   a token verifier returning the same `Principal`, so `rbac`, `tools` and `audit` don't change.
4. **Scopes:** one scope per tool family (`bookings.read`, `credits.request`, `credits.approve`, `audit.read`), checked
   in `rbac.require` alongside the role, so a token for a narrow integration can't use everything its user could.
5. **Per-person accountability:** the audit log's `subject` becomes a real staff identity (hashed), and offboarding
   in the IdP removes access everywhere.

## Key rotation (until SSO)

- Rotate every 90 days and whenever someone with access leaves: `python scripts/make_keys.py`, then update each
  client's config.
- A leaked key: rotate immediately, then read `get_audit_log` for that role's calls since the leak.

## Audit retention

- The audit log is append-only and hash-chained; `get_audit_log` reports whether the chain is intact.
- Keep it at least as long as the client's finance records need for credits (often 13 months), separately from the
  30-day request logs of stages 1–2. Archive old segments read-only and start a new chain that records the hash
  of the archived segment's last record.
