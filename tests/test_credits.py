"""Credits: front desk up to $50 is issued, above waits for a manager; only a manager approves."""

import pytest

from hotel_tools.tools import call


def credit(ctx, amount, booking="BR-1042"):
    return call(ctx, "issue_credit_request", {"booking_id": booking, "amount_usd": amount, "reason": "noise"})


def test_front_desk_threshold(make_ctx):
    fd = make_ctx("front_desk")
    assert credit(fd, 50)["status"] == "issued"
    assert credit(fd, 50.01)["status"] == "pending_manager_approval"


def test_manager_approves_directly_and_approves_pending(make_ctx):
    fd, mgr = make_ctx("front_desk"), make_ctx("manager")
    assert credit(mgr, 300)["status"] == "approved"
    pending = credit(fd, 75)
    assert call(fd, "approve_credit_request", {"request_id": pending["request_id"]})["error"].startswith(
        "the front_desk role may not"
    )
    approved = call(mgr, "approve_credit_request", {"request_id": pending["request_id"]})
    assert approved == {"request_id": pending["request_id"], "status": "approved", "amount_usd": 75.0}
    again = call(mgr, "approve_credit_request", {"request_id": pending["request_id"]})
    assert again["error"] == "credit request is approved, not waiting for approval"


@pytest.mark.parametrize("amount", [0, -5, 20_000])
def test_bad_amounts(make_ctx, amount):
    assert "amount_usd must be" in credit(make_ctx("front_desk"), amount)["error"]


def test_reason_required_and_unknown_booking(make_ctx):
    fd = make_ctx("front_desk")
    no_reason = call(fd, "issue_credit_request", {"booking_id": "BR-1042", "amount_usd": 10, "reason": " "})
    assert no_reason["error"] == "a reason is required"
    assert credit(fd, 10, booking="BR-9999")["error"] == "booking 'BR-9999' not found"
    assert call(make_ctx("manager"), "approve_credit_request", {"request_id": "REQ-NOPE"})["error"].endswith(
        "not found"
    )
