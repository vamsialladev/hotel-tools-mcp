# Video script: Hotel Tools MCP Server (about 85 seconds)

How I talk in this one: like I'm showing it to someone on a call. Short sentences, contractions, a pause where
there's a `/`. Talk from the bullets, not word for word. One take with a small stumble is fine.

Before recording: the live web demo (or `streamlit run demo_app.py`), awake, browser zoom 125%, a new conversation.
No keys on screen.

## Shot list

| Time | On screen | What I say |
|---|---|---|
| 0–10 s | The demo, role "Front desk" in the sidebar | Every AI tool at this hotel group needed the same rules. / Who can see a booking, who can give a credit. / So I put the tools in one MCP server, with roles. Simulated hotel, made-up data. |
| 10–30 s | Type input 1. Open "Steps", then the `issue_credit_request` call. Point at "Recorded for staff" | I'm the front desk. / I ask for a seventy-five dollar credit. / Claude calls the credit tool through MCP, / and the server says: pending manager approval. / Front desk can only do fifty. / So it's recorded for a manager, not given. |
| 30–45 s | Switch role to "Guest". Type input 2. Point at the bracketed source | Now I'm a guest. / Four tools, no credits at all. / I ask if I can bring my dog. / The answer comes from the hotel's own pet policy, and it says which one. |
| 45–60 s | Type input 3 | Then a follow-up. / And at Mountain Lodge? / It knows I mean the pet policy, / searches the other property, and the rules are different there. |
| 60–75 s | Switch to "Auditor". Type input 4 | And the auditor sees every call, / with a hash chain, so nobody can quietly delete one. / On my test cases the agent passed every check, including the ones that try to trick it. |
| 75–85 s | New tab: the live URL loading | It's live. / Pick a role and try to break it. The link's below. |

## Exact inputs

| # | Role | Type exactly |
|---|---|---|
| 1 | Front desk | `Booking BR-1042 had a noisy night. Issue a $75 credit.` |
| 2 | Guest | `Can I bring my dog to Beach Resort?` |
| 3 | Guest | `And at Mountain Lodge?` |
| 4 | Auditor | `Show me the last 10 tool calls.` |

Checked 2026-10-24 with the live model on a local run of this branch: input 1 is eval case d10, input 2 is d01,
input 3 is d20 (follow-up), input 4 is d15; all pass 3/3 in the saved dev run. Input 2 was also typed in the
browser: a cited answer, one MCP call, "And at Mountain Lodge?" offered next. Type all four on the live app once
it's deployed, before recording.

## LinkedIn caption (one sentence)

I built an MCP server for a hotel group where the role decides which tools even exist, and a web demo where
Claude calls them so you can watch every step.

## AI narration (used in docs/video/demo-ai-voice.mp4)

Until I record my own voice, the demo video (1:11) is narrated by an AI voice (Kokoro `af_heart`, local) and labelled "AI-narrated" on screen and here. It was recorded from the official MCP Inspector 2.10.1 (`npx -y @modelcontextprotocol/inspector@2.10.1`), connected over stdio to a local copy of this server as the guest role, with synthetic data with Playwright; the captions are the narration, timed to the voice. `/` marks a pause.

| Step | Narration |
|---|---|
| intro | This is the hotel group's tool server, inside the official MCP Inspector, / a standard client anyone can use. / I'm connecting with a guest's key, and all the data is made up. |
| tools | A guest sees four tools. / Front-desk staff would see five, and a manager six. / The role decides which tools even exist. |
| policy | I'll ask the policy search whether I can bring my dog to the beach resort. / It returns the passages with their source, / and a note that the text is reference data, never instructions. |
| other | Now I'll try someone else's booking. / The server says it doesn't exist, / so a guest can't even find out that it's there. |
| own | My own booking works, / and it shows only what a guest is allowed to see. / No name, no email, no phone number. |
| proof | Every call is checked against the role and written to an audit log. / In the eval, ninety-nine out of ninety-nine checks pass, across three runs. / And the server calls no model, so a call costs nothing. |
| end | The code is on GitHub, and the link's below. |
