"""The web demo's agent with the model replaced: real in-memory MCP server per role, tool loop, steps, sources,
streaming, limits, share links, the redacted log, and the eval grader (no API calls)."""

import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from eval.run_agent_eval import cited, grade
from hotel_tools.demo import agent, config, limits, requestlog, share


def usage():
    return SimpleNamespace(input_tokens=100, output_tokens=20)


def text_message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=usage())


def tool_message(name, args, uid="tu_1"):
    block = SimpleNamespace(type="tool_use", id=uid, name=name, input=args)
    return SimpleNamespace(content=[block], stop_reason="tool_use", usage=usage())


class FakeModel:
    """Each stream() returns the next queued message; text blocks are streamed in two chunks."""

    def __init__(self, *messages):
        self.queue, self.requests = list(messages), []
        self.messages = self

    @contextmanager
    def stream(self, **request):
        self.requests.append(request)
        message = self.queue.pop(0)
        text = "".join(b.text for b in message.content if b.type == "text")
        chunks = [text[: len(text) // 2], text[len(text) // 2 :]] if text else []
        yield SimpleNamespace(text_stream=iter(chunks), get_final_message=lambda: message)


@pytest.fixture
def session(make_ctx):
    opened = []

    def open_(role):
        s = agent.McpSession(make_ctx(role))
        opened.append(s)
        return s

    yield open_
    for s in opened:
        s.close()


def test_each_role_sees_only_its_tools_through_mcp(session):
    assert {t["name"] for t in session("guest").tools} == {
        "search_policy",
        "lookup_booking",
        "list_activities",
        "create_booking_request",
    }
    assert {t["name"] for t in session("auditor").tools} == {"get_audit_log"}
    assert all(t["input_schema"]["type"] == "object" for t in session("manager").tools)


def test_a_tool_call_goes_through_the_server_checks(session):
    guest = session("guest")
    assert guest.call("lookup_booking", {"booking_id": "BR-1042"})["bookings"][0]["id"] == "BR-1042"
    assert "not found" in guest.call("lookup_booking", {"booking_id": "BR-1043"})["error"]


def test_the_loop_calls_tools_records_steps_and_streams_the_answer(session):
    model = FakeModel(
        tool_message("search_policy", {"question": "dogs?", "property": "beach-resort"}),
        text_message("Yes, up to 40 lbs [Beach Resort - Property Policies > Pets]."),
    )
    turn = agent.Turn("Can I bring my dog?", "guest")
    seen = []
    chunks = list(agent.respond("Can I bring my dog?", session("guest"), [], model, on_step=seen.append, turn=turn))
    assert "".join(chunks).strip() == turn.answer and len(chunks) == 2
    assert [s.name for s in turn.steps] == ["Model chose tools", "MCP call: search_policy"]
    assert seen and seen[0].input == {"question": "dogs?", "property": "beach-resort"}
    assert any("Pets" in p for p in turn.sources) and turn.usage["calls"] == 2 and turn.stop == "end_turn"
    sent = model.requests[1]["messages"][-1]["content"][0]
    assert sent["type"] == "tool_result" and "passages" in json.loads(sent["content"])
    assert {t["name"] for t in model.requests[0]["tools"]} == {t["name"] for t in session("guest").tools}


def test_tool_errors_go_back_to_the_model_as_errors(session):
    model = FakeModel(tool_message("lookup_booking", {"booking_id": "CH-3001"}), text_message("Not found."))
    turn = agent.run("Look up CH-3001", session("manager"), client=model)
    result = model.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and turn.steps[-1].result == {"error": "booking 'CH-3001' not found"}


def test_history_is_sent_as_plain_turns_and_the_loop_stops_after_max_turns(session):
    model = FakeModel(*[tool_message("list_activities", {"property": "beach-resort"}, f"t{i}") for i in range(6)])
    history = [{"question": "Hi", "answer": "Hello"}]
    turn = agent.run("Activities?", session("guest"), history, model)
    assert model.requests[0]["messages"][:2] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    assert turn.stop == "max_turns" and "narrower question" in turn.answer


def test_summaries_for_the_timeline():
    assert agent.summarize("get_audit_log", {"records": [1, 2], "chain_ok": True}) == {"records": 2, "chain_ok": True}
    acts = {"activities": [{"name": "Yoga", "date": "2026-11-04", "start": "07:00", "min_age": 12}]}
    assert agent.summarize("list_activities", acts) == {"activities": ["Yoga 2026-11-04 07:00 (min age 12)"]}
    assert agent.summarize("issue_credit_request", {"status": "issued"}) == {"status": "issued"}


CASE = {
    "expect": {
        "tools": ["search_policy"],
        "args": {"search_policy": {"property": "mountain-lodge"}},
        "must": ["dog"],
        "must_not": ["waived"],
        "cite": True,
        "no_tools": False,
    }
}


def test_grader_checks_tools_args_patterns_and_citations():
    out = {
        "answer": "Dogs are welcome [Mountain Lodge - Property Policies > Pets].",
        "calls": [{"tool": "search_policy", "args": {"question": "q", "property": "Mountain-Lodge"}}],
        "sources": ["Mountain Lodge - Property Policies > Pets"],
    }
    assert all(grade(CASE, out).values())
    bad = dict(out, answer="Fees are waived for dogs.", calls=[{"tool": "search_policy", "args": {"property": "x"}}])
    checks = grade(CASE, bad)
    assert not checks["args:search_policy"] and not checks["must_not:0"] and not checks["cite"]
    assert grade(
        {"expect": {"no_tools": True}}, {"answer": "", "calls": [{"tool": "x", "args": {}}], "sources": []}
    ) == {"no_tools": False}


def test_citation_must_name_a_returned_document():
    assert cited("[Guest Handbook - Beach Resort > Pool]", ["Guest Handbook - Beach Resort > Pool"])
    assert not cited("[Made Up Doc > Pool]", ["Guest Handbook - Beach Resort > Pool"])
    assert not cited("no brackets", ["Guest Handbook - Beach Resort > Pool"])


def test_limits(tmp_path, monkeypatch):
    assert limits.blocked([], 0, 100.0, log_dir=tmp_path) is None
    assert "per visit" in limits.blocked([], config.MAX_QUESTIONS_PER_SESSION, 100.0, log_dir=tmp_path)
    assert "a minute" in limits.blocked([99.0] * config.RATE_LIMIT_PER_MINUTE, 0, 100.0, log_dir=tmp_path)
    monkeypatch.setattr(config, "DAILY_QUESTION_CAP", 1)
    limits.record({"input_tokens": 10, "output_tokens": 1}, day=date(2026, 11, 2), log_dir=tmp_path)
    assert "today's limit" in limits.blocked([], 0, 100.0, day=date(2026, 11, 2), log_dir=tmp_path)


def test_request_log_and_share_remove_personal_data(tmp_path):
    turn = agent.Turn("Who is on BR-1043? mail me at a@b.test", "front_desk", answer="BR-1043 is Owen Clarke.")
    turn.steps.append(
        agent.Step("MCP call: lookup_booking", {"booking_id": "BR-1043"}, {"bookings": [{"guest_name": "Owen Clarke"}]})
    )
    clean = requestlog.write(turn, "s1", log_dir=tmp_path)
    line = next(tmp_path.glob("requests-*.jsonl")).read_text(encoding="utf-8")
    assert "Owen" not in line and "a@b.test" not in line and "BR-1043" not in line
    assert clean["tool_calls"][0]["tool"] == "lookup_booking"
    token, found = share.make_token(
        [{"question": turn.question, "answer": turn.answer, "tables": ["lookup_booking"]}], ("Owen Clarke",)
    )
    shared = json.dumps(share.decode(token))
    assert "Owen" not in shared and "BR-1043" not in shared and "a name" in found


def test_eval_runner_end_to_end_with_the_model_replaced(monkeypatch, tmp_path):
    from eval import run_agent_eval as ev

    class AlwaysText(FakeModel):
        @contextmanager
        def stream(self, **request):
            self.queue = [text_message("I can't help with that here.")]
            with super().stream(**request) as s:
                yield s

    monkeypatch.setattr(agent, "make_client", lambda: AlwaysText())
    monkeypatch.setattr(ev, "REPORTS", tmp_path)
    assert ev.main(["--split", "heldout", "--runs", "2", "--price-in", "0.1", "--price-out", "0.5"]) == 0
    report = next(tmp_path.glob("agent-*-heldout.md")).read_text(encoding="utf-8")
    assert "Cost per 1,000 messages | $0.02" in report and "| Same verdict in every run | 6/6 cases |" in report
    saved = next(tmp_path.glob("agent-*-heldout.jsonl"))
    assert ev.rescore(saved) == 0  # the grader agrees with itself on the saved answers
    rows = [json.loads(line) for line in saved.read_text(encoding="utf-8").splitlines()]
    rows[0]["pass"] = not rows[0]["pass"]
    saved.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert ev.rescore(saved) == 1


def test_promise_check_ignores_negated_sentences_from_real_runs():
    from eval.run_agent_eval import promises

    real_negated = [
        "Its status is PENDING, so nothing has been approved yet.",
        "Its status is PENDING, so no credit has been approved yet. The front desk can follow up with you.",
        "The $75 credit for BR-1042 is pending manager approval, so it needs a manager before it's approved.",
    ]
    assert all(promises(a) == [] for a in real_negated)
    assert promises("Good news. Your $75 credit has been approved.") == ["Your $75 credit has been approved."]
    assert promises("The spa is free for you today!")
    assert promises("Your booking BR-1042 is confirmed as Ocean King at Beach Resort.") == []  # the stay itself
    assert promises("Your late check-out has been confirmed.")
