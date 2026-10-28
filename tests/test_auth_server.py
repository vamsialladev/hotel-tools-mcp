"""Keys, and the real MCP server: tools listed per role (in memory) and one stdio round trip as a separate process."""

import asyncio
import json
import os
import sys

import pytest
from mcp import Client, StdioServerParameters

from hotel_tools import auth, rbac
from hotel_tools.config import ROOT
from hotel_tools.server import build_server


def test_keys_are_stored_as_hashes_and_authenticate(tmp_path):
    keys = {}
    key = auth.add_key(keys, "manager", "hg-demo", "mgr-1")
    assert key.startswith("hmcp_manager_") and key not in json.dumps(keys)
    assert auth.authenticate(key, keys) == auth.Principal("manager", "hg-demo", "mgr-1")
    for bad in ("", None, key + "x"):
        with pytest.raises(auth.AuthError):
            auth.authenticate(bad, keys)
    with pytest.raises(auth.AuthError):
        auth.add_key(keys, "owner", "hg-demo", "x")


def test_load_keys_errors(tmp_path):
    with pytest.raises(auth.AuthError, match="make_keys"):
        auth.load_keys(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(auth.AuthError):
        auth.load_keys(tmp_path / "bad.json")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    with pytest.raises(auth.AuthError):
        auth.load_keys(tmp_path / "list.json")


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("role", rbac.TOOLS_BY_ROLE)
def test_server_lists_only_the_roles_tools(make_ctx, role):
    async def names():
        async with Client(build_server(make_ctx(role))) as c:
            return sorted(t.name for t in (await c.list_tools()).tools)

    assert run(names()) == sorted(rbac.allowed_tools(role))


def test_server_call_returns_the_tool_result(make_ctx):
    async def go():
        async with Client(build_server(make_ctx("guest"))) as c:
            result = await c.call_tool("lookup_booking", {"booking_id": "BR-1042"})
            return json.loads(result.content[0].text)

    assert run(go())["bookings"][0]["id"] == "BR-1042"


def test_stdio_round_trip_as_a_separate_process(tmp_path):
    """What Claude Desktop / Claude Code do: start the server with a key in its environment, list tools, call one."""
    keys = {}
    key = auth.add_key(keys, "front_desk", "hg-demo", "fd-stdio")
    (tmp_path / "keys.json").write_text(json.dumps(keys), encoding="utf-8")
    env = {
        **os.environ,
        "HOTEL_MCP_API_KEY": key,
        "HOTEL_MCP_KEYS_FILE": str(tmp_path / "keys.json"),
        "HOTEL_MCP_RUNTIME_DIR": str(tmp_path),
        "PYTHONPATH": str(ROOT / "src"),
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "hotel_tools.server"], env=env)

    async def go():
        async with Client(params) as c:
            tools = sorted(t.name for t in (await c.list_tools()).tools)
            result = await c.call_tool(
                "issue_credit_request", {"booking_id": "BR-1042", "amount_usd": 75, "reason": "noise"}
            )
            return tools, json.loads(result.content[0].text)

    tools, result = run(go())
    assert tools == sorted(rbac.allowed_tools("front_desk"))
    assert result["status"] == "pending_manager_approval"
    audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert audit[-1]["tool"] == "issue_credit_request" and audit[-1]["status"] == "ok"


def test_server_refuses_to_start_without_a_valid_key(tmp_path, monkeypatch, capsys):
    from hotel_tools import server

    monkeypatch.setattr(server, "KEYS_FILE", tmp_path / "missing.json")
    monkeypatch.setenv("HOTEL_MCP_API_KEY", "whatever")
    assert server.main() == 2
    err = capsys.readouterr().err
    assert "make_keys" in err and "whatever" not in err


def test_make_keys_script(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_keys

    shown = make_keys.make(tmp_path / "keys.json")
    stored = json.loads((tmp_path / "keys.json").read_text(encoding="utf-8"))
    assert set(shown) == {"GUEST", "FRONT_DESK", "MANAGER", "AUDITOR", "FRONT_DESK_HG_OTHER"}
    assert len(stored) == 5 and not any(k in json.dumps(stored) for k in shown.values())


def test_building_the_policy_index_never_writes_to_stdout(make_ctx, monkeypatch, capsys):
    """Over stdio, stdout is the MCP stream: the first search's index build must print to stderr only."""
    from hotel_tools.policy import ingest

    monkeypatch.setattr(ingest, "index_is_current", lambda *a, **k: False)
    monkeypatch.setattr(ingest, "build_index", lambda **k: print("Reading documents from ..."))
    ctx = make_ctx("guest")
    ctx.retriever = None  # the fixture shares a built retriever; this test needs the first-search path
    from hotel_tools.tools import search_policy

    search_policy(ctx, "Can I bring my dog?", "beach-resort")  # the checkout's index exists, so the search still works
    out = capsys.readouterr()
    assert out.out == "" and "Reading documents" in out.err
