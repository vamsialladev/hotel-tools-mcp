"""The seven tools as plain functions, plus `call()`: rate limit -> role check -> tool -> audit record, for every call.

The MCP server (server.py) only exposes these; tests, the eval and the demo script call them directly too, so there
is one code path. A tool never moves money or confirms a booking: it records a request for a person to act on.
"""

import contextlib
import sys
from dataclasses import dataclass, field

from hotel_tools import guard, rbac
from hotel_tools.audit import AuditLog
from hotel_tools.auth import Principal
from hotel_tools.config import FRONT_DESK_CREDIT_LIMIT, MAX_RESULTS
from hotel_tools.ratelimit import RateLimited, RateLimiter
from hotel_tools.store import Store

REQUEST_TYPES = ("late_checkout", "early_checkin", "room_change", "activity", "other")


class Invalid(ValueError):
    """Bad arguments or an unknown record. The message is safe to return."""


@dataclass
class Context:
    principal: Principal
    store: Store
    audit: AuditLog
    limiter: RateLimiter
    retriever: object = None  # hotel_tools.policy.retrieve.Retriever, built lazily
    extra: dict = field(default_factory=dict)


def _property(ctx: Context, prop: str) -> str:
    prop = (prop or "").strip().lower()
    if prop not in ctx.store.properties(ctx.principal.hotel_group_id):
        raise Invalid(f"unknown property {prop!r} for this hotel group")
    return prop


def _booking(ctx: Context, booking_id: str) -> dict:
    """The caller's tenant only; a guest only their own bookings. Anything else is 'not found' (no existence leak)."""
    p = ctx.principal
    booking = ctx.store.booking(p.hotel_group_id, booking_id)
    if booking is None or (p.role == "guest" and booking["guest_email"].lower() != p.subject.lower()):
        raise Invalid(f"booking {booking_id!r} not found")
    return booking


def search_policy(ctx: Context, question: str, property: str) -> dict:
    prop = _property(ctx, property)
    if not question or not question.strip():
        raise Invalid("question is empty")
    if ctx.retriever is None:
        from hotel_tools.policy.ingest import build_index, index_is_current
        from hotel_tools.policy.retrieve import Retriever

        if not index_is_current(False):
            # Over stdio, stdout is the MCP stream: the build's progress lines go to stderr, or they corrupt it.
            with contextlib.redirect_stdout(sys.stderr):
                build_index(use_embeddings=False)
        ctx.retriever = Retriever(use_embeddings=False)
    from hotel_tools.policy.config import TOP_K

    staff = rbac.sees_staff_documents(ctx.principal)
    if staff:  # staff roles: exactly the stage 1 search
        hits = ctx.retriever.search(question[:500], prop)
    else:  # a guest: ask for more, drop staff-only documents, keep the usual number
        hits = ctx.retriever.search(question[:500], prop, k=TOP_K * 2)
        hits = [h for h in hits if h["source"] not in rbac.STAFF_ONLY_SOURCES][:TOP_K]
    passages, removed = [], 0
    for h in hits:
        text, flagged = guard.quarantine(h["text"])
        removed += flagged
        passages.append({"source": h["source"], "section": h["section"], "property": h["property"], "text": text})
    return {"passages": passages, "instructions_removed": removed, "note": guard.DATA_NOTE}


def lookup_booking(ctx: Context, booking_id: str = "", guest_email: str = "") -> dict:
    p = ctx.principal
    if booking_id:
        found = [_booking(ctx, booking_id)]
    elif guest_email or p.role == "guest":
        email = p.subject if p.role == "guest" else guest_email  # a guest can only look up themselves
        found = ctx.store.bookings_for(p.hotel_group_id, email)
    else:
        raise Invalid("give a booking_id or a guest_email")
    views = []
    for b in found[:MAX_RESULTS]:
        view = rbac.booking_view(p, b)
        if "notes" in view:
            view["notes"], _ = guard.quarantine(view["notes"])
        views.append(view)
    return {"bookings": views, "note": guard.DATA_NOTE}


def list_activities(ctx: Context, property: str, date: str = "", age: int | None = None) -> dict:
    prop = _property(ctx, property)
    out = []
    for a in ctx.store.activities_for(ctx.principal.hotel_group_id, prop):
        if date and a["date"] != date:
            continue
        if age is not None and age < a["min_age"]:
            continue
        description, _ = guard.quarantine(a["description"])
        out.append(
            {
                "id": a["id"],
                "name": a["name"],
                "date": a["date"],
                "start": a["start"],
                "end": a["end"],
                "spots_left": max(a["capacity"] - a["booked"], 0),
                "min_age": a["min_age"],
                "price_usd": a["price_usd"],
                "description": description,
            }
        )
    return {"activities": out[:MAX_RESULTS], "note": guard.DATA_NOTE}


def create_booking_request(ctx: Context, booking_id: str, request_type: str, details: str = "") -> dict:
    if request_type not in REQUEST_TYPES:
        raise Invalid(f"request_type must be one of {', '.join(REQUEST_TYPES)}")
    booking = _booking(ctx, booking_id)
    rec = ctx.store.append_request(
        ctx.principal.hotel_group_id,
        {
            "kind": "booking_request",
            "booking_id": booking["id"],
            "request_type": request_type,
            "details": details[:500],
            "status": "PENDING",
            "by_role": ctx.principal.role,
        },
    )
    return {
        "request_id": rec["id"],
        "status": "PENDING",
        "note": "Recorded for staff. Nothing is booked or confirmed yet.",
    }


def issue_credit_request(ctx: Context, booking_id: str, amount_usd: float, reason: str) -> dict:
    """Front desk: up to the limit is issued (recorded for posting); above it waits for a manager. Manager: approved."""
    if not 0 < amount_usd <= 10_000:
        raise Invalid("amount_usd must be between 0 and 10,000")
    if not reason or not reason.strip():
        raise Invalid("a reason is required")
    booking = _booking(ctx, booking_id)
    role = ctx.principal.role
    if role == "manager":
        status = "approved"
    elif amount_usd <= FRONT_DESK_CREDIT_LIMIT:
        status = "issued"
    else:
        status = "pending_manager_approval"
    rec = ctx.store.append_request(
        ctx.principal.hotel_group_id,
        {
            "kind": "credit",
            "booking_id": booking["id"],
            "amount_usd": round(float(amount_usd), 2),
            "reason": reason[:300],
            "status": status,
            "by_role": role,
        },
    )
    return {"request_id": rec["id"], "status": status, "amount_usd": rec["amount_usd"]}


def approve_credit_request(ctx: Context, request_id: str) -> dict:
    current = ctx.store.requests(ctx.principal.hotel_group_id).get((request_id or "").strip())
    if current is None or current.get("kind") != "credit":
        raise Invalid(f"credit request {request_id!r} not found")
    if current["status"] != "pending_manager_approval":
        raise Invalid(f"credit request is {current['status']}, not waiting for approval")
    rec = ctx.store.append_request(
        ctx.principal.hotel_group_id, {**current, "status": "approved", "approved_by_role": "manager"}
    )
    return {"request_id": rec["id"], "status": "approved", "amount_usd": rec["amount_usd"]}


def get_audit_log(ctx: Context, limit: int = 50, tool: str = "", status: str = "") -> dict:
    records = ctx.audit.read(ctx.principal.hotel_group_id, min(max(limit, 1), 500), tool or None, status or None)
    return {"records": records, "chain_ok": ctx.audit.verify()}


TOOLS = {
    "search_policy": search_policy,
    "lookup_booking": lookup_booking,
    "list_activities": list_activities,
    "create_booking_request": create_booking_request,
    "issue_credit_request": issue_credit_request,
    "approve_credit_request": approve_credit_request,
    "get_audit_log": get_audit_log,
}


def call(ctx: Context, tool: str, args: dict) -> dict:
    """Every call: rate limit, role check, run, one audit record. Errors come back as {"error": ...}, never a trace."""
    try:
        ctx.limiter.check(ctx.principal)
        rbac.require(ctx.principal, tool)
        result = TOOLS[tool](ctx, **args)
        status, detail = "ok", result.get("status", "")
    except RateLimited as exc:
        result, status, detail = {"error": str(exc)}, "rate_limited", ""
    except rbac.Denied as exc:
        result, status, detail = {"error": str(exc)}, "denied", ""
    except (Invalid, TypeError) as exc:
        message = str(exc) if isinstance(exc, Invalid) else "invalid arguments"
        result, status, detail = {"error": message}, "invalid", message
    except Exception:  # noqa: BLE001 - never leak internals to the client
        result, status, detail = {"error": "internal error; it was logged"}, "error", ""
    ctx.audit.record(ctx.principal, tool, args, status, str(detail))
    return result
