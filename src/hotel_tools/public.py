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
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from hotel_tools.auth import Principal
from hotel_tools.server import build_server, make_context

PUBLIC_PRINCIPAL = Principal(role="guest", hotel_group_id="hg-demo", subject="elena.ruiz@mail.test")
READ_ONLY_EXCLUDE = frozenset({"create_booking_request"})
MCP_PATH = "/mcp"
CONNECT_PAGE = "https://vamsialla.com/projects/hotel-tools-mcp-connect.html"
REPO = "https://github.com/vamsialladev/hotel-tools-mcp"
HOME = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Hotel Tools MCP Server · public demo endpoint</title>
<style>body{{font:18px/1.6 system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;color:#1C1F1D;
background:#F7F4EE}}a{{color:#1E4636}}code{{background:#fff;padding:2px 6px;border-radius:4px}}</style></head>
<body><h1>Hotel Tools MCP Server</h1>
<p>This is a public, read-only demo of an MCP server for a <strong>fictional hotel group with synthetic data</strong>.
It isn't a web page to browse: MCP clients connect to <code>{MCP_PATH}</code>.</p>
<p>You're connected as one made-up guest, with three read-only tools: policy search, activities, and that guest's own
bookings. No key is needed, nothing can be written, and each instance allows 10 calls a minute.</p>
<p><a href="{CONNECT_PAGE}">How to connect with an MCP client →</a><br><a href="{REPO}">Code on GitHub →</a></p>
<p>Free hosting: the first call after a quiet spell may take a moment to wake.</p>
</body></html>"""


async def home(request: Request) -> HTMLResponse:
    """A short page at / so a visitor's browser doesn't land on "Not Found"."""
    return HTMLResponse(HOME)


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
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH, stateless_http=True, json_response=True, transport_security=security
    )
    app.router.routes.append(Route("/", home, methods=["GET"]))
    return app
