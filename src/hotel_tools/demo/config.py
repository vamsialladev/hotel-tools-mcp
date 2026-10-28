"""Settings for the web demo (demo_app.py), from environment variables or Streamlit secrets. README: Configuration."""

import os
from pathlib import Path

from hotel_tools.config import ROOT

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # the MCP server itself doesn't need python-dotenv
    pass


def _float(name: str, default: str) -> float:
    return float(os.getenv(name) or default)


LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "low")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
LOG_DIR = Path(os.getenv("DEMO_LOG_DIR", ROOT / ".hotel-mcp" / "demo-logs"))
MAX_QUESTIONS_PER_SESSION = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "20"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "6"))
DAILY_QUESTION_CAP = int(os.getenv("DAILY_QUESTION_CAP", "300"))
DAILY_COST_CAP_USD = _float("DAILY_COST_CAP_USD", "1.00")
# Used for the daily cost cap only. Defaults: Claude Haiku 5.5 list price, USD per million tokens (2026-10).
PRICE_IN_PER_M = _float("PRICE_IN_PER_M", "0.10")
PRICE_OUT_PER_M = _float("PRICE_OUT_PER_M", "0.50")
DEMO_VIDEO_URL = os.getenv("DEMO_VIDEO_URL", "")
REPO_URL = "https://github.com/vamsialladev/hotel-tools-mcp"
PORTFOLIO_URL = "https://vamsialla.com"
