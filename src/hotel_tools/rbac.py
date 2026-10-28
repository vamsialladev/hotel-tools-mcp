"""Who may call which tool and see which fields. One table, checked on every call (and used to decide which tools
the server registers at all, so a role never even sees a tool it can't use)."""

from hotel_tools.auth import Principal

TOOLS_BY_ROLE = {
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

# Booking fields each role sees. A guest sees only their own bookings (checked in tools.lookup_booking).
BOOKING_FIELDS = {
    "guest": ("id", "property", "check_in", "check_out", "room_type", "tier"),
    "front_desk": (
        "id",
        "property",
        "check_in",
        "check_out",
        "room_type",
        "tier",
        "guest_name",
        "guest_email",
        "phone_last4",
    ),
    "manager": (
        "id",
        "property",
        "check_in",
        "check_out",
        "room_type",
        "tier",
        "guest_name",
        "guest_email",
        "guest_phone",
        "rate_usd",
        "notes",
    ),
}

# Policy documents written for staff, not guests: search_policy leaves them out for the guest role. Stage 1 is a
# staff tool, so it indexes them on purpose; this server also answers guests (the stage 6 concierge connects as one).
# tests/test_rbac.py checks that every raw document marked confidential or internal is listed here.
STAFF_ONLY_SOURCES = frozenset(
    {
        "mountain-lodge/events_weddings.pdf",  # "CONFIDENTIAL - INTERNAL STAFF USE ONLY"
        "mountain-lodge/front_desk_notes.txt",  # staff notes ("never promise it at booking")
        "shared/housekeeping_sop.md",  # a staff procedure
    }
)


def sees_staff_documents(principal: Principal) -> bool:
    return principal.role != "guest"


class Denied(Exception):
    """The caller's role may not do this. The message is safe to return to the client."""


def allowed_tools(role: str) -> set[str]:
    return set(TOOLS_BY_ROLE.get(role, set()))


def require(principal: Principal, tool: str) -> None:
    if tool not in TOOLS_BY_ROLE.get(principal.role, set()):
        raise Denied(f"the {principal.role} role may not use {tool}")


def booking_view(principal: Principal, booking: dict) -> dict:
    full = {**booking, "phone_last4": (booking.get("guest_phone") or "")[-4:]}
    return {f: full.get(f) for f in BOOKING_FIELDS[principal.role]}
