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
| LLM01 | Prompt injection | Instruction-like text removed from tool results; the server never executes model output |
| LLM02 | Sensitive information disclosure | Field views per role; guests see only their own bookings; tenant scoping; redacted audit |
| LLM03 | Supply chain | Pinned dependencies, pip-audit and gitleaks in CI, Dependabot; stage 1 code copied at a pinned tag and checked |
| LLM04 | Data and model poisoning | Documents come from a pinned copy checked in CI; planted instructions in data are stripped |
| LLM05 | Improper output handling | Typed tool schemas; arguments validated; results are JSON data |
| LLM06 | Excessive agency | Tools only record requests; credits above $50 need a manager; nothing is posted or confirmed |
| LLM07 | System prompt leakage | No secrets in server instructions or results |
| LLM08 | Vector and embedding weaknesses | Keyword search filtered by property and tenant; no shared vector store across tenants |
| LLM09 | Misinformation | Policy answers come with their source passages; the server adds no generated text |
| LLM10 | Unbounded consumption | Rate limits per key; result sizes capped; the web demo adds per-visit, per-minute and daily caps and a 6-turn limit |

Known limitations: demo API keys (docs/AUTH.md), pattern-based injection guard, local files rather than a database.
