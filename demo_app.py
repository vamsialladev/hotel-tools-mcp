"""Web demo of the Hotel Tools MCP server: pick a role, chat, and watch Claude call the server's tools.

The MCP server runs in-process with synthetic data. Each role gets its own server with only that role's tools,
exactly as with an API key in Claude Desktop. Requests and the audit log live in a private folder for this browser
session, so visitors never see each other's activity.

streamlit run demo_app.py
"""

import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402
import streamlit as st  # noqa: E402

from hotel_tools import rbac  # noqa: E402
from hotel_tools.audit import AuditLog  # noqa: E402
from hotel_tools.auth import Principal  # noqa: E402
from hotel_tools.config import DATA_DIR, RATE_LIMITS  # noqa: E402
from hotel_tools.demo import agent, limits, requestlog, share  # noqa: E402
from hotel_tools.demo.config import DEMO_VIDEO_URL, PORTFOLIO_URL, REPO_URL  # noqa: E402
from hotel_tools.ratelimit import RateLimiter  # noqa: E402
from hotel_tools.store import Store  # noqa: E402
from hotel_tools.tools import Context  # noqa: E402

st.set_page_config(page_title="Hotel Tools MCP demo", page_icon="🔐", layout="wide")
ROLE_LABELS = {
    "guest": "Guest (Elena, booking BR-1042)",
    "front_desk": "Front desk",
    "manager": "Manager",
    "auditor": "Auditor",
}
SUBJECTS = {"guest": "elena.ruiz@mail.test", "front_desk": "fd-1", "manager": "mgr-1", "auditor": "aud-1"}
EXAMPLES = {
    "guest": [
        "Can I bring my dog to Beach Resort?",
        "What's on at Beach Resort on 2026-11-04 for a 6-year-old?",
        "Please request a late check-out for my booking.",
    ],
    "front_desk": [
        "Booking BR-1042 had a noisy night. Issue a $75 credit.",
        "What do the notes on booking BR-1044 say?",
        "What is the pet policy at Mountain Lodge?",
    ],
    "manager": [
        "Booking BR-1042 had a noisy night. Issue a $75 credit.",
        "What's the phone number on booking BR-1043?",
        "Look up booking CH-3001.",
    ],
    "auditor": ["Show me the last 10 tool calls.", "Were any calls denied?", "Look up booking BR-1042."],
}
NEXT = {
    "search_policy": ["And at Mountain Lodge?"],
    "lookup_booking": ["Can I get a late check-out on that booking?"],
    "list_activities": ["Which of those are good for a 6-year-old?"],
    "issue_credit_request": ["Switch to Manager and approve it."],
    "create_booking_request": ["What happens next with that request?"],
    "get_audit_log": ["Is the audit chain intact?"],
}
FRIENDLY_ERROR = "The model didn't answer in time. Please try again in a minute."


@st.cache_resource(show_spinner="Loading the policy index (first visit after a restart takes a few seconds)...")
def retriever():
    from hotel_tools.policy.ingest import build_index, index_is_current
    from hotel_tools.policy.retrieve import Retriever

    if not index_is_current(False):
        build_index(use_embeddings=False)
    return Retriever(use_embeddings=False)


def state():
    s = st.session_state
    s.setdefault("session_id", uuid.uuid4().hex[:12])
    s.setdefault("runtime", tempfile.mkdtemp(prefix="hotel-mcp-demo-"))
    s.setdefault("sessions", {})  # role -> agent.McpSession
    s.setdefault("conversations", {})  # id -> {"title", "role", "turns"}
    s.setdefault("current", None)
    s.setdefault("asked", 0)
    s.setdefault("times", [])
    return s


def mcp_session(role: str) -> agent.McpSession:
    s = state()
    if role not in s.sessions:
        runtime = Path(s.runtime)
        ctx = Context(
            Principal(role, "hg-demo", SUBJECTS[role]),
            Store(DATA_DIR, runtime),
            AuditLog(runtime / "audit.jsonl"),
            RateLimiter(RATE_LIMITS),
        )
        ctx.retriever = retriever()
        s.sessions[role] = agent.McpSession(ctx)
    return s.sessions[role]


def current_turns() -> list[dict]:
    s = state()
    return s.conversations.get(s.current, {}).get("turns", [])


def new_conversation():
    s = state()
    s.current = None
    s.pop("share_link", None)


def show_steps(steps: list[dict]):
    for i, step in enumerate(steps, 1):
        st.markdown(f"**{i}. {step['name']}** · {step['seconds']:.2f} s")
        st.json({"input": step["input"], "result": step["result"]}, expanded=False)


def show_turn(turn: dict):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"] or "_(no answer)_")
        if turn["sources"]:
            st.caption("Policy passages searched: " + " · ".join(dict.fromkeys(turn["sources"])))
        calls = [s for s in turn["steps"] if s["name"].startswith("MCP call")]
        if turn["steps"]:
            label = f"Steps: {len(calls)} MCP call(s) · {turn['seconds']:.1f} s · {turn['calls']} model call(s)"
            with st.expander(label):
                show_steps(turn["steps"])


def turn_dict(turn: agent.Turn) -> dict:
    return {
        "question": turn.question,
        "role": turn.role,
        "answer": turn.answer,
        "sources": turn.sources,
        "steps": [vars(s) for s in turn.steps],
        "tables": [s.name.removeprefix("MCP call: ") for s in turn.steps if s.name.startswith("MCP call")],
        "seconds": turn.seconds,
        "calls": turn.usage["calls"],
        "names": list(requestlog.names_in(turn)),
    }


def answer(question: str, role: str):
    s = state()
    reason = limits.blocked(s.times, s.asked, time.time())
    if reason:
        st.info(reason, icon=":material/hourglass:")
        return
    s.asked += 1
    s.times = [t for t in s.times if time.time() - t < 60] + [time.time()]
    history = [{"question": t["question"], "answer": t["answer"]} for t in current_turns()]
    turn = agent.Turn(question, role)
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            session = mcp_session(role)
            status = st.status("Working on it...", expanded=False)

            def on_step(step):
                status.write(f"✓ {step.name}")

            st.write_stream(agent.respond(question, session, history, on_step=on_step, turn=turn))
            status.update(label=f"Done: {len(turn.steps)} steps", state="complete")
        except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.APIStatusError):
            st.error(FRIENDLY_ERROR, icon=":material/cloud_off:")
            return
        except Exception:  # noqa: BLE001 - never show a trace to a visitor
            st.error("Something went wrong on my side. Please try a different question.", icon=":material/error:")
            return
    limits.record(turn.usage)
    try:
        requestlog.write(turn, s.session_id)
    except OSError:
        pass
    if s.current is None:
        s.current = uuid.uuid4().hex[:8]
        s.conversations[s.current] = {"title": question[:48], "role": role, "turns": []}
    s.conversations[s.current]["turns"].append(turn_dict(turn))
    s.pop("share_link", None)
    st.rerun()


def share_box():
    turns = current_turns()
    if not turns:
        return
    if st.button("Share this conversation", icon=":material/link:"):
        names = tuple(n for t in turns for n in t.get("names", []))
        token, found = share.make_token(turns, names)
        state().share_link = {"token": token, "found": found}
    link = state().get("share_link")
    if link and link["token"]:
        st.caption("Read-only link (the conversation is inside the link; nothing is stored):")
        st.code(share.share_url(st.context.url, link["token"]), language=None, wrap_lines=True)
        if link["found"]:
            st.caption("Replaced before sharing: " + ", ".join(link["found"]) + ".")
    elif link:
        st.caption("This conversation is too long to share as a link.")


def requests_box():
    store = Store(DATA_DIR, Path(state().runtime))
    reqs = list(store.requests("hg-demo").values())
    if reqs:
        with st.expander(f"Recorded for staff in this visit ({len(reqs)})", icon=":material/pending_actions:"):
            st.caption("Nothing is booked, paid or confirmed: these wait for a person.")
            cols = ("id", "kind", "booking_id", "request_type", "amount_usd", "status", "by_role")
            st.dataframe([{k: r.get(k, "") for k in cols} for r in reqs], hide_index=True)


def chat_page(role: str):
    tools = ", ".join(f"`{t}`" for t in sorted(rbac.allowed_tools(role)))
    st.write(
        f"You're signed in as **{ROLE_LABELS[role]}**. This role's MCP server exposes {tools}; the model can't see "
        "any other tool. Data is synthetic."
    )
    turns = current_turns()
    for turn in turns:
        show_turn(turn)
    picked = None
    used = turns[-1]["tables"] if turns else []
    options = EXAMPLES[role] if not turns else [q for t in used for q in NEXT.get(t, [])][:3]
    asked = {t["question"] for t in turns}
    options = [q for q in dict.fromkeys(options) if q not in asked]
    if options:
        st.caption("Try:" if not turns else "Next:")
        cols = st.columns(len(options))
        for i, (col, q) in enumerate(zip(cols, options, strict=True)):
            if col.button(q, key=f"suggest-{role}-{len(turns)}-{i}", use_container_width=True):
                picked = q
    requests_box()
    share_box()
    question = st.chat_input(f"Ask as {ROLE_LABELS[role].split(' (')[0].lower()}...") or picked
    if question:
        answer(question, role)


def shared_page(token: str):
    st.title("🔐 Hotel Tools MCP · shared conversation")
    st.caption("Read-only copy. Names, contact details and booking IDs were replaced before sharing. Synthetic data.")
    turns = share.decode(token)
    if not turns:
        st.warning("This link is damaged or from a different version of the app.", icon=":material/link_off:")
    for t in turns or []:
        with st.chat_message("user"):
            st.text(t["q"])
        with st.chat_message("assistant"):
            st.text(t["a"])
            if t["t"]:
                st.caption("Tools called: " + ", ".join(t["t"]))
    st.link_button("Try it yourself", "?", icon=":material/chat:")


def on_role_change():
    new_conversation()


def sidebar() -> str:
    s = state()
    with st.sidebar:
        role = st.radio(
            "Role",
            list(ROLE_LABELS),
            format_func=ROLE_LABELS.get,
            key="role",
            on_change=on_role_change,
            help="Each role is a different API key: different tools, different fields.",
        )
        st.divider()
        st.button("New conversation", icon=":material/add:", on_click=new_conversation, use_container_width=True)
        if s.conversations:
            st.caption("Conversations (this browser tab)")
        for cid, conv in reversed(list(s.conversations.items())):
            label = ("▸ " if cid == s.current else "") + f"{conv['title']} · {conv['role']}"
            if st.button(label, key=f"conv-{cid}", use_container_width=True, disabled=conv["role"] != role):
                s.current = cid
                s.pop("share_link", None)
                st.rerun()
        st.divider()
        if DEMO_VIDEO_URL:
            st.link_button("Watch the 90-second demo", DEMO_VIDEO_URL, icon=":material/play_circle:")
        st.link_button("About this project (GitHub)", REPO_URL, icon=":material/code:")
        st.link_button("Portfolio", PORTFOLIO_URL, icon=":material/person:")
        st.caption("Stage 7 of a simulated client engagement. Synthetic data, no real guests.")
    return role


token = st.query_params.get("share")
if token:
    shared_page(token)
    st.stop()
st.title("🔐 Hotel Tools MCP")
st.caption("Stage 7 · one MCP server, four roles, every call checked and audited · synthetic data")
chat_page(sidebar())
