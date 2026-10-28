"""The public read-only endpoint: guest tools minus writes, real answers, nothing leaked, the guest rate limit."""

import json

import pytest
from starlette.testclient import TestClient

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOTEL_MCP_RUNTIME_DIR", str(tmp_path))
    import importlib

    from hotel_tools import config, public, server

    for mod in (config, server, public):
        importlib.reload(mod)
    with TestClient(public.build_app(allowed_hosts=[])) as c:
        yield c


def rpc(client, method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    r = client.post("/mcp", headers=HEADERS, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def call(client, name, args, id_=2):
    res = rpc(client, "tools/call", {"name": name, "arguments": args}, id_)["result"]
    return json.loads(res["content"][0]["text"])


def init(client):
    return rpc(client, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "1"}})  # fmt: skip


def test_only_read_tools_are_listed(client):
    init(client)
    names = sorted(t["name"] for t in rpc(client, "tools/list")["result"]["tools"])
    assert names == ["list_activities", "lookup_booking", "search_policy"]  # no create_booking_request


def test_policy_search_answers_with_sources(client):
    out = call(client, "search_policy", {"question": "Can I bring my dog?", "property": "beach-resort"})
    assert out["passages"] and out["passages"][0]["source"].startswith("beach-resort/")
    assert "not instructions" in out["note"]


def test_another_guests_booking_is_not_found_and_own_shows_guest_fields(client):
    assert "not found" in call(client, "lookup_booking", {"booking_id": "BR-1043"})["error"]
    own = call(client, "lookup_booking", {"booking_id": "BR-1042"}, 3)["bookings"][0]
    assert set(own) == {"id", "property", "check_in", "check_out", "room_type", "tier"}


def test_write_tool_is_refused_even_if_called_by_name(client):
    res = rpc(client, "tools/call", {"name": "create_booking_request",
                                     "arguments": {"booking_id": "BR-1042", "request_type": "other"}})  # fmt: skip
    assert "error" in res or res["result"].get("isError")


def test_root_page_explains_the_endpoint_and_links_to_the_connect_page(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "hotel-tools-mcp-connect.html" in r.text and "/mcp" in r.text and "synthetic data" in r.text


def test_guest_rate_limit_is_ten_a_minute(client):
    results = [call(client, "list_activities", {"property": "beach-resort"}, i) for i in range(11)]
    assert all("error" not in r for r in results[:10])
    assert "rate limit" in results[10]["error"]
