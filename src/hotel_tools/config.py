"""Settings, all from environment variables (see the configuration table in the README)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_INSTALLED_DATA = Path(sys.prefix) / "share" / "hotel-tools-mcp" / "data"  # pyproject [tool.setuptools.data-files]
# A source checkout is recognised by its pyproject.toml, not by a data/ folder (an installed copy's index build once
# created site-packages/../data, which then looked like a checkout).
DATA_DIR = Path(
    os.getenv("HOTEL_MCP_DATA_DIR") or (ROOT / "data" if (ROOT / "pyproject.toml").exists() else _INSTALLED_DATA)
)
# Where requests and the audit log are written. Git-ignored; one folder per installation.
RUNTIME_DIR = Path(os.getenv("HOTEL_MCP_RUNTIME_DIR", ROOT / ".hotel-mcp"))
KEYS_FILE = Path(os.getenv("HOTEL_MCP_KEYS_FILE", RUNTIME_DIR / "keys.json"))
API_KEY_ENV = "HOTEL_MCP_API_KEY"  # the key the MCP client passes to this server process

# Calls allowed per key per minute, by role.
RATE_LIMITS = {
    "guest": int(os.getenv("RATE_LIMIT_GUEST", "10")),
    "front_desk": int(os.getenv("RATE_LIMIT_FRONT_DESK", "60")),
    "manager": int(os.getenv("RATE_LIMIT_MANAGER", "60")),
    "auditor": int(os.getenv("RATE_LIMIT_AUDITOR", "30")),
}
RATE_WINDOW_S = 60.0
FRONT_DESK_CREDIT_LIMIT = float(os.getenv("FRONT_DESK_CREDIT_LIMIT", "50"))  # brand standard: up to $50
MAX_RESULTS = 20
