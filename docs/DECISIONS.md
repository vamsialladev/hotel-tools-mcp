# Decisions

Each: context, decision, tradeoff, result.

## 1. The official MCP Python SDK's `MCPServer` (formerly FastMCP)

- **Context:** the plan said FastMCP. In `mcp` 2.x the SDK's FastMCP class was renamed `MCPServer` (installing
  `mcp` 2.3.0 and importing `mcp.server.fastmcp` raises an error pointing to the rename).
- **Decision:** use `mcp.server.mcpserver.MCPServer` from the official SDK (same decorator-style API), not the
  separate `fastmcp` package.
- **Tradeoff:** a newer API with fewer examples online.
- **Result:** works over stdio and in memory; one test runs the server as a separate process like Claude Desktop does.

## 2. One server process per key; register only the role's tools

- **Context:** a role check inside each tool is necessary, but the client's model would still see tools it can't
  use, try them, and get confused.
- **Decision:** authenticate at start, register only the role's tools, and keep the check in `tools.call()` too.
- **Tradeoff:** a process per key doesn't scale to thousands of guests (HTTP + OAuth is the path; docs/AUTH.md).
- **Result:** a guest sees 4 tools, an auditor 1; tests list tools per role through a real MCP client.

## 3. Another tenant's record is "not found"

- **Context:** "access denied" for another hotel group's booking ID would confirm the ID exists.
- **Decision:** every read takes the caller's `hotel_group_id`; anything else is indistinguishable from a missing
  record. A guest asking for someone else's booking gets the same answer.
- **Tradeoff:** support staff can't tell "wrong group" from "typo" from the error alone (the audit log can).
- **Result:** isolation tests and 15 eval checks pass, including a guest whose email exists in both groups.

## 4. Strip planted instructions from tool results in the server

- **Context:** stage 2 quarantined planted instructions inside its agent. Here the data goes to clients I don't
  control.
- **Decision:** the server removes instruction-like sentences from passages, booking notes and activity
  descriptions, reports how many, and says in every result that results are data.
- **Tradeoff:** pattern-based; a new phrasing can get through. A false positive removes a harmless sentence.
- **Result:** the staff note, the booking note and the activity description never reach the client in the eval.

## 5. Hash-chained, redacted audit log, written for every call

- **Context:** IT asked for "who asked what, when, and what the system did", and an audit log people can edit
  proves little.
- **Decision:** append-only JSONL; each record stores the previous record's hash; arguments are stored as a SHA-256,
  details are redacted with stage 1's `pii.scrub_text`; denied and failed calls are audited too.
- **Tradeoff:** a hash of the arguments can't be read back; investigating needs the original request.
- **Result:** tests show editing one record breaks `verify()`, and no email or phone appears in the file.

## 6. Copy stage 1's search instead of depending on it

- **Context:** same choice as stage 2 (its decision 1): a live dependency on another app's repo is fragile.
- **Decision:** `scripts/sync_policy.py` copies `retrieve.py`, `ingest.py`, `pii.py` and the documents at stage 1's
  v1.6.0 tag; CI fails if the copy changes.
- **Tradeoff:** fixes in stage 1 need a re-sync here.
- **Result:** 45/45 of stage 1's labelled questions retrieve the expected passage through `search_policy`, the
  same as stage 1.

## 7. A failed check on an empty list is a bug in the check

- **Context:** the first eval run scored 97%: case t05 (an auditor of the second group reads the log) failed
  because that group had no audit records yet, and the check compared an empty set to the expected group.
- **Decision:** the check now fails on an empty list, and the case first makes a call in each group.
- **Tradeoff:** none.
- **Result:** 99/99 dev, 18/18 held-out.
