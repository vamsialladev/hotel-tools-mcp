"""Every role x every tool: allowed calls run, denied calls are refused and audited. Field-level views per role."""

import pytest

from hotel_tools import rbac
from hotel_tools.tools import TOOLS, call

ARGS = {
    "search_policy": {"question": "Can a guest bring their dog?", "property": "beach-resort"},
    "lookup_booking": {"booking_id": "BR-1042"},
    "list_activities": {"property": "beach-resort"},
    "create_booking_request": {"booking_id": "BR-1042", "request_type": "late_checkout"},
    "issue_credit_request": {"booking_id": "BR-1042", "amount_usd": 20, "reason": "slow check-in"},
    "approve_credit_request": {"request_id": "REQ-NONE"},
    "get_audit_log": {},
}
EXPECTED = {
    "guest": {"search_policy", "lookup_booking", "list_activities", "create_booking_request"},
    "front_desk": {
        "search_policy",
        "lookup_booking",
        "list_activities",
        "create_booking_request",
        "issue_credit_request",
    },
    "manager": {
        "search_policy",
        "lookup_booking",
        "list_activities",
        "create_booking_request",
        "issue_credit_request",
        "approve_credit_request",
    },
    "auditor": {"get_audit_log"},
}


def test_the_table_is_what_the_spec_says():
    assert {r: rbac.allowed_tools(r) for r in EXPECTED} == EXPECTED
    assert set(ARGS) == set(TOOLS)


@pytest.mark.parametrize("role", EXPECTED)
@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_every_role_and_tool(make_ctx, role, tool):
    ctx = make_ctx(role)
    result = call(ctx, tool, ARGS[tool])
    record = ctx.audit.read("hg-demo", 1)[0]
    if tool in EXPECTED[role]:
        assert "may not use" not in result.get("error", "")
        assert record["status"] in ("ok", "invalid")  # approve of an unknown request is a valid refusal
    else:
        assert result == {"error": f"the {role} role may not use {tool}"}
        assert record["status"] == "denied"


def test_guest_sees_only_their_own_bookings_and_few_fields(make_ctx):
    guest = make_ctx("guest")
    own = call(guest, "lookup_booking", {"booking_id": "BR-1042"})["bookings"][0]
    assert set(own) == {"id", "property", "check_in", "check_out", "room_type", "tier"}
    assert call(guest, "lookup_booking", {"booking_id": "ML-2001"}) == {"error": "booking 'ML-2001' not found"}
    mine = call(guest, "lookup_booking", {"guest_email": "hannah.berg@mail.test"})  # asks for someone else
    assert sorted(b["id"] for b in mine["bookings"]) == ["BR-1042", "ML-2003"]  # still only their own


def test_staff_field_views(make_ctx):
    fd = call(make_ctx("front_desk"), "lookup_booking", {"booking_id": "BR-1042"})["bookings"][0]
    assert fd["guest_name"] == "Elena Ruiz" and fd["phone_last4"] == "0142"
    assert "guest_phone" not in fd and "rate_usd" not in fd and "notes" not in fd
    mgr = call(make_ctx("manager"), "lookup_booking", {"booking_id": "BR-1042"})["bookings"][0]
    assert mgr["guest_phone"] == "+1 305 555 0142" and mgr["rate_usd"] == 289 and "Biscuit" in mgr["notes"]


def test_staff_look_up_by_email_and_need_an_argument(make_ctx):
    fd = make_ctx("front_desk")
    assert [b["id"] for b in call(fd, "lookup_booking", {"guest_email": "HANNAH.BERG@mail.test"})["bookings"]] == [
        "ML-2001"
    ]
    assert call(fd, "lookup_booking", {}) == {"error": "give a booking_id or a guest_email"}


def test_guest_requests_only_for_their_own_booking(make_ctx):
    guest = make_ctx("guest")
    ok = call(guest, "create_booking_request", {"booking_id": "br-1042", "request_type": "late_checkout"})
    assert ok["status"] == "PENDING"
    denied = call(guest, "create_booking_request", {"booking_id": "BR-1043", "request_type": "late_checkout"})
    assert denied == {"error": "booking 'BR-1043' not found"}
    bad = call(guest, "create_booking_request", {"booking_id": "BR-1042", "request_type": "free_upgrade"})
    assert "request_type must be one of" in bad["error"]


def test_unexpected_arguments_are_invalid_not_a_crash(make_ctx):
    assert call(make_ctx("front_desk"), "lookup_booking", {"nope": 1}) == {"error": "invalid arguments"}
