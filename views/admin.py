"""Owner only: the shared ops view (hotel-ai-platform) with its own sign-in (ADMIN_PASSWORD, 5 tries then a 15-minute
lock). Registered by demo_app.py only when ADMIN_PASSWORD is set, and hidden from the menu until signed in. The audit
log of MCP calls stays per browser session, by design: visitors never see each other's activity."""

from hotelplatform import admin_ui

from hotel_tools.demo import ops

admin_ui.render(
    ops.store(),
    app_title="Hotel Tools MCP demo",
    version=ops.running_version(),
    dependencies=ops.dependencies,
    **ops.caps(),
)
