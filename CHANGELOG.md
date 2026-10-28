# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]
### Added
- A public read-only demo endpoint (`asgi.py`, `hotel_tools.public`): Streamable HTTP, stateless, one synthetic guest, no write tools, 10 calls a minute (decision 15).
- A short page at `/` on the public endpoint that explains it and links to the connect page.

## [1.2.0] - 2026-10-25
### Security
- `search_policy` leaves staff-only documents out for the guest role (decision 13).
### Fixed
- The first search's index build printed to stdout, which corrupts the stdio MCP stream (decision 14).
### Added
- Web demo: shared guardrails, tracing and ops log from [hotel-ai-platform](https://github.com/vamsialladev/hotel-ai-platform)
  v0.1.2 (decision 12): input check before any model turn, output check against the turn's MCP results, one trace per
  question (model turns, MCP calls), "Reference: ..." on errors, hidden Admin page (`ADMIN_PASSWORD`, shared lockout),
  JSON startup logs, privacy note, `?source=keepawake` runs nothing.
- Red-team suite in CI (`scripts/run_redteam.py`, docs/RED_TEAM.md) and a CycloneDX SBOM artifact.
### Changed
- The server's quarantine also uses the shared patterns when they're installed (red-team rt31, m05).
- The synthetic data ships with the package (`[tool.setuptools.data-files]`), so another app can install the server
  and run it in-process; `DATA_DIR` falls back to that copy when there's no source checkout.

## [1.1.0] - 2026-10-24

### Added

- Web demo (`demo_app.py`): pick a role and chat; Claude Haiku 5.5 calls the server's tools through an in-memory
  MCP client, with a step timeline, cited policy answers, follow-ups, past conversations, read-only share links,
  a "Recorded for staff" table, per-session requests and audit log, limits, and a redacted log.
- Agent eval for the demo: 22 dev + 6 held-out cases, 3 runs, saved reports, `--rescore [--write]`.

## [1.0.0] - 2026-10-24

### Added

- MCP server (official SDK `MCPServer`, stdio) with 7 tools: `search_policy`, `lookup_booking`, `list_activities`,
  `create_booking_request`, `issue_credit_request`, `approve_credit_request`, `get_audit_log`.
- Roles (guest, front_desk, manager, auditor) by API key; only the role's tools are registered; field views per role;
  front-desk credits up to $50, managers approve above.
- Tenant isolation by `hotel_group_id`; planted-instruction removal in tool results; per-key rate limits;
  append-only, hash-chained, redacted audit log.
- Stage 1's search and redaction copied at v1.6.0 (`scripts/sync_policy.py`, checked in CI).
- Labelled eval (33 dev + 6 held-out cases, 3 runs), demo script for three roles, docs, CI.
