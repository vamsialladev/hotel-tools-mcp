"""The same request as three roles: what each one is allowed to do, through the real tool code (no model, no keys).

    python scripts/demo_roles.py

"Booking BR-1042: the room was noisy last night. Can we get a $75 credit and a late check-out?"
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hotel_tools.audit import AuditLog  # noqa: E402
from hotel_tools.auth import Principal  # noqa: E402
from hotel_tools.config import DATA_DIR, RATE_LIMITS  # noqa: E402
from hotel_tools.ratelimit import RateLimiter  # noqa: E402
from hotel_tools.store import Store  # noqa: E402
from hotel_tools.tools import Context, call  # noqa: E402

QUESTION = "Booking BR-1042: the room was noisy last night. Can we get a $75 credit and a late check-out?"
STEPS = [
    ("lookup_booking", {"booking_id": "BR-1042"}),
    ("issue_credit_request", {"booking_id": "BR-1042", "amount_usd": 75, "reason": "noise complaint"}),
    ("create_booking_request", {"booking_id": "BR-1042", "request_type": "late_checkout", "details": "noisy night"}),
]
ROLES = [("guest", "elena.ruiz@mail.test"), ("front_desk", "fd-1"), ("manager", "mgr-1")]


def outcome(tool: str, result: dict) -> str:
    if "error" in result:
        return f"refused: {result['error']}"
    if tool == "lookup_booking":
        b = result["bookings"][0]
        return f"found, {len(b)} fields" + (" (incl. phone, rate, notes)" if "rate_usd" in b else "")
    return f"{result['status']} ({result['request_id']})"


def run() -> list[tuple[str, str, str]]:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        for role, subject in ROLES:
            ctx = Context(
                Principal(role, "hg-demo", subject),
                Store(DATA_DIR, runtime),
                AuditLog(runtime / "audit.jsonl"),
                RateLimiter(RATE_LIMITS),
            )
            rows += [(role, tool, outcome(tool, call(ctx, tool, args))) for tool, args in STEPS]
        auditor = Context(
            Principal("auditor", "hg-demo", "aud-1"),
            Store(DATA_DIR, runtime),
            AuditLog(runtime / "audit.jsonl"),
            RateLimiter(RATE_LIMITS),
        )
        log = call(auditor, "get_audit_log", {"limit": 20})
        rows.append(("auditor", "get_audit_log", f"{len(log['records'])} records, chain intact: {log['chain_ok']}"))
    return rows


def main() -> int:
    print(f'Request: "{QUESTION}"\n')
    print("| Role | Tool | Outcome |\n|---|---|---|")
    for role, tool, result in run():
        print(f"| {role} | {tool} | {result} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
