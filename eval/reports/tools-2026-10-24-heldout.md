# Tool server eval: heldout (2026-10-24)

- Cases: 6 × 3 runs · every run agreed: yes
- Pass rate: **100%** (18/18)
- Latency per tool call (in process, no network): p50 1.7 ms, p95 23.1 ms
- Cost per 1,000 calls: $0.00 (no model is called by this server)

| Category | Pass |
|---|---|
| credit_threshold | 3/3 |
| field_level | 3/3 |
| injection_in_results | 3/3 |
| role_denied | 6/6 |
| tenant_isolation | 3/3 |

Failing: none
