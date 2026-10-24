"""Tenant isolation: a key for one hotel group can't read or change another group's records, even knowing the IDs."""

from hotel_tools.tools import call


def test_no_cross_tenant_booking_reads(make_ctx):
    other = make_ctx("front_desk", tenant="hg-other", subject="other-fd")
    assert call(other, "lookup_booking", {"booking_id": "BR-1042"}) == {"error": "booking 'BR-1042' not found"}
    by_email = call(other, "lookup_booking", {"guest_email": "elena.ruiz@mail.test"})
    assert [b["id"] for b in by_email["bookings"]] == ["CH-3002"]  # same email, only their own group's booking
    demo = make_ctx("front_desk")
    assert call(demo, "lookup_booking", {"booking_id": "CH-3001"}) == {"error": "booking 'CH-3001' not found"}


def test_a_guest_of_two_groups_sees_only_the_group_of_their_key(make_ctx):
    guest = make_ctx("guest", tenant="hg-other", subject="elena.ruiz@mail.test")
    assert [b["id"] for b in call(guest, "lookup_booking", {})["bookings"]] == ["CH-3002"]


def test_properties_and_activities_are_per_tenant(make_ctx):
    other = make_ctx("front_desk", tenant="hg-other", subject="other-fd")
    assert "unknown property" in call(other, "list_activities", {"property": "beach-resort"})["error"]
    assert "unknown property" in call(other, "search_policy", {"question": "dogs", "property": "beach-resort"})["error"]
    assert [a["id"] for a in call(other, "list_activities", {"property": "city-hotel"})["activities"]] == ["A-301"]


def test_no_cross_tenant_approval(make_ctx):
    fd = make_ctx("front_desk")
    pending = call(fd, "issue_credit_request", {"booking_id": "BR-1042", "amount_usd": 80, "reason": "noise"})
    other_mgr = make_ctx("manager", tenant="hg-other", subject="other-mgr")
    assert call(other_mgr, "approve_credit_request", {"request_id": pending["request_id"]})["error"].endswith(
        "not found"
    )
    assert fd.store.requests("hg-other") == {}


def test_a_forged_tenant_in_a_record_is_overwritten(make_ctx):
    ctx = make_ctx("front_desk")
    rec = ctx.store.append_request("hg-demo", {"kind": "credit", "hotel_group_id": "hg-other", "status": "issued"})
    assert rec["hotel_group_id"] == "hg-demo"


def test_audit_log_is_per_tenant(make_ctx):
    call(make_ctx("front_desk"), "lookup_booking", {"booking_id": "BR-1042"})
    call(make_ctx("front_desk", tenant="hg-other", subject="other-fd"), "lookup_booking", {"booking_id": "CH-3001"})
    demo = call(make_ctx("auditor"), "get_audit_log", {})["records"]
    other = call(make_ctx("auditor", tenant="hg-other", subject="other-aud"), "get_audit_log", {})["records"]
    assert {r["hotel_group_id"] for r in demo} == {"hg-demo"}
    assert {r["hotel_group_id"] for r in other} == {"hg-other"}
