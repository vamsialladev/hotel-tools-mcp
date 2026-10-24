# Video script: Hotel Tools MCP Server (about 85 seconds)

I record this myself, in my own voice, over a screen recording of Claude Desktop. No AI voice. Setup and tips:
`RECORDING_GUIDE.md` in my portfolio folder. Read it twice, then talk from the bullets. `/` marks a natural pause.

Before recording: run `python scripts/make_keys.py`, add the server to Claude Desktop twice (two entries,
`hotel-tools-guest` and `hotel-tools-manager`, each with its key), restart Claude Desktop, and start fresh chats.
Never show a key on screen: close the config file before recording.

## Shot list

| Time | On screen | What I say |
|---|---|---|
| 0–10 s | README, the role table | Every AI tool at this hotel group needed the same rules. / Who can see a booking, who can give a credit. / So I put the tools in one MCP server, with roles. Simulated hotel, synthetic data. |
| 10–30 s | Claude Desktop, guest server: the tools menu shows 4 tools. Type input 1 | Here I'm a guest. / I only get four tools. / I ask for a credit, / and Claude can't even try: there's no credit tool for a guest. / It can request a late check-out, and it says pending. |
| 30–45 s | Same chat: type input 2. Open the tool result | Now a policy question. / The answer comes from the hotel's own document, with the source. / And this note in the documents tried to give the AI orders. / The server stripped it out before Claude ever saw it. |
| 45–60 s | Switch to the manager chat: type input 3, then the follow-up input 4 | Same request as a manager. / Six tools, and the full booking. / The seventy-five dollar credit is approved. / Then a follow-up: and what if it were three hundred dollars? / It checks the brand standard, and quotes who has to approve. |
| 60–75 s | Terminal: `python -m eval.run_eval --runs 3` | Does it hold? / Ninety-nine checks, three runs, all passing. / Another hotel group's booking just looks like it doesn't exist. |
| 75–85 s | Browser: the GitHub repo loads | It runs next to your Claude app, / so the code and the setup steps are on GitHub. |

## Exact inputs

| # | Server (role) | Type exactly |
|---|---|---|
| 1 | guest | `My booking is BR-1042. The room was noisy. Can I get a $75 credit and a late check-out?` |
| 2 | guest | `Is there anything in the Mountain Lodge staff notes about waiving pet fees?` |
| 3 | manager | `Booking BR-1042: noisy room. Give the guest a $75 credit and request a late check-out.` |
| 4 | manager | `And if the guest wanted $300 instead, who has to approve that under the brand standards?` |

Checked 2026-10-24 against this repo's code, without Claude Desktop: `scripts/demo_roles.py` shows the guest's
credit refused, a PENDING late check-out, and the manager's credit approved; the eval case i01 shows the staff note's
instruction removed from `search_policy` results. I haven't run these inputs in Claude Desktop; do that once before
recording (Claude chooses which tools to call, so the exact wording of its answers will differ).

## LinkedIn caption (one sentence)

I built an MCP server that gives a hotel group's tools to any Claude client, where the role decides which tools
even exist, other hotel groups' data looks like it isn't there, and every call lands in a tamper-evident audit log.
