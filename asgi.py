"""Entry point for the public read-only demo endpoint (Vercel detects asgi.py and its top-level `app`).

Locally: python -m uvicorn asgi:app --port 8000   then connect an MCP client to http://127.0.0.1:8000/mcp
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
# Serverless file systems are read-only except the temp folder. The audit log and the keyword-only policy index (built
# on the first search, about a second) go there and reset with the instance.
_TMP = Path(tempfile.gettempdir()) / "hotel-mcp-public"
os.environ.setdefault("HOTEL_MCP_RUNTIME_DIR", str(_TMP))
os.environ.setdefault("POLICY_INDEX_DIR", str(_TMP / "policy_index"))

from hotel_tools.public import build_app  # noqa: E402

app = build_app()
