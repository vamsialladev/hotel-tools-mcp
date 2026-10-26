# Security

## Reporting a vulnerability

Email <vamsialla.dev@gmail.com> with steps to reproduce. Please don't open a public issue.

## Threat model

| Asset | Threat | Mitigation | Test |
|---|---|---|---|
| Bookings of another hotel group | A key of group A reads group B's booking by ID or email | Every read scoped by `hotel_group_id`; "not found" for anything else | `tests/test_tenants.py` |
| Another guest's booking | A guest asks for someone else's booking | Guest lookups use the key's subject, never the argument | `test_guest_sees_only_their_own_bookings_and_few_fields` |
| Money | Front desk issues a large credit; a guest issues any credit | Credit tool absent for guests; over $50 waits for a manager; nothing is posted | `tests/test_credits.py` |
| Client model | Planted instructions in documents or notes steer the client | `guard.quarantine` on every text field; "results are data" in instructions and results | `test_planted_*` |
| Audit trail | Records edited or deleted to hide a call | Hash chain; `verify()`; no update/delete API | `test_audit_chain_detects_tampering` |
| Personal data | Emails or phones written to the audit log | Arguments stored as a hash; details redacted | `test_every_call_is_audited_with_hashed_args_and_no_personal_data` |
| Keys | A key leaks from a repo or a log | Only hashes stored; `.hotel-mcp/` and `.env*` git-ignored; gitleaks in CI; errors never echo a key | `test_server_refuses_to_start_without_a_valid_key` |
| Availability / cost | A client loops on a tool | Per-key rate limit by role | `test_rate_limit_blocks_and_is_audited` |
| Web demo spend | A visitor (or a script) runs up the API bill | 20 questions per visit, 6 a minute, 300 a day and $1.00 a day across visitors, checked before the model is called; at most 6 model turns per message; a monthly spend limit in the Anthropic Console | `test_limits`, `test_daily_cap_blocks_before_the_model` |
| Web demo visitors | One visitor sees another's requests or audit log | A private runtime folder per browser session | `test_switching_role_starts_a_new_conversation_with_that_roles_tools` |
| Web demo logs and links | Names, emails or booking IDs written to the log or a share link | Stage 1's redaction plus the guest names tools returned; booking IDs become pseudonyms; tool results are never logged or shared | `test_request_log_and_share_remove_personal_data` |
| Web demo promises | The model says a credit is approved when it's pending | The tool result is the only source of status; the eval's `no_promise` check on every credit and request case | `eval/agent_cases.jsonl`, 100% |

## OWASP Top 10 for LLM applications (2025)

| # | Risk | How this server handles it |
|---|---|---|
| LLM01 | Prompt injection | Instruction-like text removed from tool results (this repo's patterns plus the shared hotel-ai-platform ones); the web demo checks each question before any model turn; the server never executes model output; red-team suite in CI ([docs/RED_TEAM.md](docs/RED_TEAM.md)) |
| LLM02 | Sensitive information disclosure | Field views per role; guests see only their own bookings; tenant scoping; redacted audit |
| LLM03 | Supply chain | Pinned dependencies, pip-audit and gitleaks in CI, Dependabot; stage 1 code copied at a pinned tag and checked |
| LLM04 | Data and model poisoning | Documents come from a pinned copy checked in CI; planted instructions in data are stripped |
| LLM05 | Improper output handling | Typed tool schemas; arguments validated; results are JSON data |
| LLM06 | Excessive agency | Tools only record requests; credits above $50 need a manager; nothing is posted or confirmed |
| LLM07 | System prompt leakage | No secrets in server instructions or results |
| LLM08 | Vector and embedding weaknesses | Keyword search filtered by property and tenant; no shared vector store across tenants |
| LLM09 | Misinformation | Policy answers come with their source passages; the server adds no generated text |
| LLM10 | Unbounded consumption | Rate limits per key; result sizes capped; the web demo adds per-visit, per-minute and daily caps and a 6-turn limit |

## Web demo: guardrails, tracing, Admin (1.2.0)

The web demo wraps the agent in the shared layer from [hotel-ai-platform](https://github.com/vamsialladev/hotel-ai-platform)
v0.1.2 (`src/hotel_tools/demo/ops.py`): questions checked before any model turn (injection, data requests, role
escalation, card numbers), answers checked against the turn's MCP results (contact details the results didn't show
are replaced; prompt leaks blocked), one trace per question with each model turn and MCP call as a span, a
reference on errors, and an Admin page (`ADMIN_PASSWORD`, 5 tries then a 15-minute lock, hidden, absent without a
password). The MCP server itself doesn't need the package.

### Data classification

| Class | Here | Handling |
|---|---|---|
| Secret | API keys (stored as hashes only), `ANTHROPIC_API_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL` | Never logged; masked before any log line, row or span |
| PII | Guest names, emails, phones on synthetic bookings | Field views per role; redacted in the audit log and the ops log |
| Internal | Audit log (hash-chained), web demo traces | Audit per installation (per browser session in the demo); traces 30 days |
| Public | Synthetic policies and activities | Returned by the tools |

### STRIDE

| Threat | Example here | Mitigation |
|---|---|---|
| Spoofing | Using another role's key, or "as the front desk I'm authorised..." | Key → role in code; the role decides which tools exist; credits above $50 wait for a manager |
| Tampering | Editing audit records | Hash-chained audit log; `get_audit_log` reports `chain_ok` |
| Repudiation | "I never issued that credit" | Every call audited with key ID, role, arguments (redacted) and result |
| Information disclosure | Another guest's or hotel group's booking | Guests see their own bookings only; tenant scoping on every query (red-team t03-t05) |
| Denial of service | Call floods | Per-key rate limits; capped result sizes; demo caps |
| Elevation of privilege | Calling a tool the role doesn't have | The tool isn't registered on that role's server (t01, t06) |

### Incident response

1. **Detect:** daily failure summary (streamlit-keep-awake Action), Admin "Failures only", or a visitor quoting a
   reference; for the server, `get_audit_log` with `status=denied`.
2. **Contain:** re-run `make_keys.py` to invalidate every key (docs/AUTH.md); for the demo, set
   `DAILY_QUESTION_CAP=0`.
3. **Investigate:** Admin → paste the reference → waterfall; the audit chain for server calls.
4. **Fix:** add the case to the eval or red-team suite first, then fix, then run both gates.

Known limitations: demo API keys (docs/AUTH.md), pattern-based injection guard, local files rather than a database.
