# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
