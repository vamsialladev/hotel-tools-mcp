"""Shared guardrails, request tracing and the cross-app ops log (hotel-ai-platform), wired for the web demo.

    with ops.start(session_id) as trace:             one trace per question; the reference shows on errors
        v = ops.check_question(text)                 before the model
        ...agent.respond(): each model turn and each MCP call is a span...
        o = ops.check_answer(answer, turn)           after the model, against the turn's MCP results
        ops.finish(trace, turn, status)              one ops_request_log row + the spans, PII removed first

The MCP server itself doesn't depend on this: it's the web demo's layer around the agent. What a role may do is
still decided by the server's RBAC; the guardrails stop obvious attacks before a model turn is spent on them.
"""

import os
from functools import lru_cache

from hotelplatform import guardrails, jsonlog, oplog, tracing, version

from hotel_tools.config import ROOT
from hotel_tools.demo import config, limits

APP = "hotel-tools-mcp"
APP_VERSION = "1.2.0"
MONTHLY_COST_CAP_USD = float(os.getenv("MONTHLY_COST_CAP_USD", "10.00"))

INPUT_POLICY = guardrails.InputPolicy(max_chars=1000, languages=("en", "es"))
# Promises are off: a front desk role really can issue a credit up to $50 through the server, so "I've issued a $40
# credit" is a fact, and the server's RBAC (not wording) decides what each role may do. Contact details are checked
# against the turn's MCP results, so a manager's lookup of a phone number on a booking is not a leak.
OUTPUT_POLICY = guardrails.OutputPolicy(require_citation=False, numbers="off", promises="off", pii_leak="redact")


@lru_cache(maxsize=1)
def store() -> oplog.OpsStore:
    """One per process; nothing connects until the first row (the keep-awake visit never gets that far)."""
    url = os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://", 1)
    return oplog.OpsStore(APP, url=url, log_dir=config.LOG_DIR / "ops", retention_days=30)


@lru_cache(maxsize=1)
def running_version() -> str:
    return version.version_string(APP_VERSION, ROOT)


def configure_logs() -> None:
    jsonlog.configure(APP, running_version())


def start(session_id: str | None):
    return tracing.new_trace(APP, session_id=session_id)


def check_question(text: str) -> guardrails.Verdict:
    return guardrails.check_input(text, INPUT_POLICY)


def check_answer(answer: str, tool_texts: list[str], question: str) -> guardrails.Verdict:
    return guardrails.check_output(answer, OUTPUT_POLICY, sources=tool_texts, input_text=question)


def safety_flags(trace) -> list[str]:
    flags = set()
    for span in trace.spans if trace is not None else []:
        if span.name.startswith("guardrails."):
            stage = span.name.split(".", 1)[1]
            flags.update(span.attributes.get("flags") or [])
            flags.update(f"{stage}:{r}" for r in span.attributes.get("reasons") or [])
    return sorted(flags)


def finish(trace, turn=None, status: str = "ok", error_type: str | None = None) -> bool:
    """Write the ops row for one question. Never raises, never blocks."""
    if trace is None:
        return False
    try:
        usage = getattr(turn, "usage", None) or {"input_tokens": 0, "output_tokens": 0}
        calls = [s.name.removeprefix("MCP call: ") for s in getattr(turn, "steps", []) if s.name.startswith("MCP")]
        row = oplog.request_row(
            trace,
            request_type=f"chat:{getattr(turn, 'role', 'unknown')}",
            status=status,
            latency_ms=round(getattr(turn, "seconds", 0.0) * 1000, 1) or trace.elapsed_ms(),
            error_type=error_type,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            cost_usd=limits.cost_usd(usage),
            model=config.LLM_MODEL if usage.get("calls") else None,
            tool_calls=[{"tool": c} for c in calls],
            sources=list(dict.fromkeys(getattr(turn, "sources", []))),
            safety_flags=safety_flags(trace),
            version=running_version(),
            data={
                "role": getattr(turn, "role", None),
                "question": getattr(turn, "question", None),
                "answer": getattr(turn, "answer", None),
            },  # fmt: skip
        )
        if status == "capped":
            jsonlog.cap_hit(error_type or "cap", trace_id=trace.trace_id)
        return store().submit(trace, row)
    except Exception:
        return False


def dependencies() -> dict[str, str]:
    return {
        "anthropic": "configured" if os.getenv("ANTHROPIC_API_KEY") else "missing key",
        "MCP server": "in-process (one per role per browser session)",
        "ops log": store().health()["status"],
        "model": config.LLM_MODEL,
    }


def caps() -> dict[str, float]:
    return {"cost_cap_day": config.DAILY_COST_CAP_USD, "cost_cap_month": MONTHLY_COST_CAP_USD}
