"""The public, read-only demo endpoint: the same server over Streamable HTTP, pinned to one synthetic guest.

Rules (stage 7 public demo):
- one fixed identity: the guest role in the synthetic hotel group, so no key is needed and none can be leaked;
- read-only: the guest's create_booking_request is not registered, so the endpoint can't write a request;
- the guest rate limit (RATE_LIMIT_GUEST, 10 calls a minute), counted per running instance;
- synthetic data only, and every call still goes through tools.call() (role check, rate limit, audit).

Stateless JSON responses, so it runs on serverless hosts (Vercel) where one request may land on a fresh instance.
"""

import os

from mcp.server.transport_security import TransportSecuritySettings

from hotel_tools.auth import Principal
from hotel_tools.server import build_server, make_context

PUBLIC_PRINCIPAL = Principal(role="guest", hotel_group_id="hg-demo", subject="elena.ruiz@mail.test")
READ_ONLY_EXCLUDE = frozenset({"create_booking_request"})
MCP_PATH = "/mcp"


def build_app(allowed_hosts: list[str] | None = None):
    """The ASGI app. DNS-rebinding protection guards servers on a user's own machine; this one is public, so the
    Host check is on only when PUBLIC_ALLOWED_HOSTS lists the deployed host names."""
    hosts = (
        allowed_hosts
        if allowed_hosts is not None
        else [h.strip() for h in os.getenv("PUBLIC_ALLOWED_HOSTS", "").split(",") if h.strip()]
    )
    security = TransportSecuritySettings(enable_dns_rebinding_protection=bool(hosts), allowed_hosts=hosts)
    server = build_server(make_context(PUBLIC_PRINCIPAL), exclude=READ_ONLY_EXCLUDE)
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH, stateless_http=True, json_response=True, transport_security=security
    )
