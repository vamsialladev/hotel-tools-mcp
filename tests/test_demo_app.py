"""The web demo page runs for real (AppTest) with the agent's model replaced; the MCP server is the real one."""

import pytest
from streamlit.testing.v1 import AppTest

from hotel_tools.config import ROOT
from hotel_tools.demo import agent, config, share


def fake_respond(question, session, history=None, client=None, on_step=None, turn=None):
    result = session.call("lookup_booking", {"booking_id": "BR-1042"})
    step = agent.Step("MCP call: lookup_booking", {"booking_id": "BR-1042"}, agent.summarize("lookup_booking", result))
    turn.steps.append(step)
    if on_step:
        on_step(step)
    turn.usage["calls"] = 2
    turn.answer = f"Booking BR-1042 found ({len(history or [])} earlier turns)."
    yield turn.answer


@pytest.fixture
def at(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "respond", fake_respond)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    return AppTest.from_file(str(ROOT / "demo_app.py"), default_timeout=120)


def test_page_renders_with_role_tools_and_links(at):
    at.run()
    assert not at.exception
    assert "search_policy" in at.markdown[0].value and "issue_credit_request" not in at.markdown[0].value
    assert any("synthetic" in c.value.lower() for c in at.sidebar.caption)


def test_a_question_shows_answer_steps_and_next_suggestions(at):
    at.run()
    at.chat_input[0].set_value("Show my booking").run()
    assert not at.exception
    assert any("Booking BR-1042 found (0 earlier turns)" in m.value for m in at.markdown)
    assert any(e.label.startswith("Steps: 1 MCP call(s)") for e in at.expander)
    assert any(b.label == "Can I get a late check-out on that booking?" for b in at.button)
    at.chat_input[0].set_value("And again?").run()
    assert any("(1 earlier turns)" in m.value for m in at.markdown)


def test_switching_role_starts_a_new_conversation_with_that_roles_tools(at):
    at.run()
    at.chat_input[0].set_value("Show my booking").run()
    at.sidebar.radio[0].set_value("auditor").run()
    assert at.session_state["current"] is None
    assert "get_audit_log" in at.markdown[0].value and "lookup_booking" not in at.markdown[0].value


def test_share_link(at):
    at.run()
    at.chat_input[0].set_value("Show my booking").run()
    next(b for b in at.button if b.label == "Share this conversation").click().run()
    url = next(c.value for c in at.code if "?share=" in c.value)
    turns = share.decode(url.split("?share=", 1)[1])
    assert turns[0]["q"] == "Show my booking" and "BR-1042" not in turns[0]["a"]
    shared = AppTest.from_file(str(ROOT / "demo_app.py"), default_timeout=120)
    shared.query_params["share"] = url.split("?share=", 1)[1]
    shared.run()
    assert "shared conversation" in shared.title[0].value and not shared.chat_input


def test_daily_cap_blocks_before_the_model(at, monkeypatch):
    monkeypatch.setattr(config, "MAX_QUESTIONS_PER_SESSION", 0)
    at.run()
    at.chat_input[0].set_value("Show my booking").run()
    assert any("per visit" in i.value for i in at.info) and not at.session_state["conversations"]
