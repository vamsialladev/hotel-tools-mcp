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

## 8. A web demo that goes through the real MCP protocol

- **Context:** the checklist wants a live link that works on the first click. An MCP server needs an MCP client,
  and asking a recruiter to edit Claude Desktop's config is not a first click.
- **Decision:** `demo_app.py` (Streamlit) runs `build_server(ctx)` in-process and talks to it with the SDK's
  in-memory MCP `Client`: `list_tools` for the role, `call_tool` for each call. Claude Haiku 5.5 runs a manual
  tool-use loop (at most 6 model turns) with only that role's tools. The client lives in one task on a background
  event loop, because anyio requires a client to be opened and closed in the same task (the first version failed
  with "Attempted to exit cancel scope in a different task").
- **Tradeoff:** one server per role per browser session instead of one process per key; the stdio server is
  unchanged and still tested as a separate process.
- **Result:** every demo call goes through the same rate limit, role check, field view, injection guard and audit
  record as Claude Desktop's. Page tests run the real server with the model replaced.

## 9. Follow-ups as conversation history, not a rewrite step

- **Context:** stages 1 and 8 rewrite a follow-up into a standalone question before retrieval, because retrieval
  runs before the model. Here the model writes the tool arguments itself.
- **Decision:** send the last 6 turns (text only, no old tool results) with the new message; the model resolves
  "it" and "and at Mountain Lodge?" into standalone tool arguments, which the step timeline shows.
- **Tradeoff:** a few hundred more input tokens per message than a rewrite; old tool results aren't re-sent, so
  the model calls a tool again when it needs fresh data.
- **Result:** follow-up cases d20, d21, h06: 9/9 across 3 runs (the search ran for `mountain-lodge`; "it" resolved
  to BR-1042's check-out date; "same for ML-2002, $30" issued $30 on ML-2002).

## 10. Citations must name a real source; fix the prompt, not the grader

- **Context:** first agent run: 4 of 9 policy answers cited "[Mountain Lodge > Pets]" or "[beach-resort > Pets]",
  shortened forms that don't match any document title.
- **Decision:** keep the grader strict (the bracket must contain the title of a passage `search_policy` returned)
  and tell the model to copy the passage's `section` value exactly.
- **Tradeoff:** a longer citation in the answer.
- **Result:** citations 9/9 dev and 3/3 held-out in the second run.

## 11. A promise check that understands "not yet"

- **Context:** "nothing has been approved yet" and "no credit has been approved yet" are the right answers, and a
  regular expression called them promises. Stage 2 hit the same trap with negated offers.
- **Decision:** `no_promise` checks sentence by sentence and skips sentences with a negation (no, not, nothing,
  yet, n't, until, once, unless). "Is confirmed" alone doesn't count, because "your booking is confirmed as Ocean
  King" describes the stay that exists; "has been confirmed" does. The real phrasings are unit tests.
- **Tradeoff:** a sentence that promises and negates something else ("Your credit is approved, no action needed")
  would be missed. None appeared in 84 answers; the test list grows when one does.
- **Result:** the saved second run re-scored without the model: 65/66 → 66/66; held-out unchanged at 18/18.

## 12. The web demo gets the shared guardrails, tracing and an Admin page; the server stays standalone (2026-10-25)
- **Context:** the final plan adds guardrails, a red team, tracing, one ops log and an Admin page to every live app.
  This repo is two things: an MCP server people install, and a web demo around it.
- **Decision:** the web demo wires hotel-ai-platform v0.1.2 (`src/hotel_tools/demo/ops.py`): input check before any
  model turn, output check against the turn's MCP results (contact details only; promise wording is off because the
  server's RBAC and credit limits decide what a role can do), one trace per question, an Admin page behind
  `ADMIN_PASSWORD`. The server's quarantine uses the shared patterns only if the package is installed.
- **Trade-off:** a bare MCP install keeps the narrower pattern list. Documented in SECURITY.md.
- **Result:** red team shared 48/48 (three documented overrides); own 15 held-out cases 13/15 first run, 14/15 after
  the quarantine fix; the 67 real texts the server returns are identical before and after.
