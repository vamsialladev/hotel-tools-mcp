"""One JSON line per demo question, with personal data removed BEFORE it is written (stage 1's redaction).

Recorded: time, anonymous session ID, role, question, answer, each tool call (name and arguments), the policy
sources returned, how the loop stopped, timing, tokens and cost. Not recorded: tool results. Guest names that a
tool returned are masked wherever they appear. The MCP server's own audit log records every call separately.
"""

import json
import threading
from datetime import UTC, date, datetime
from pathlib import Path

from hotel_tools.demo import config, limits
from hotel_tools.policy.pii import scrub

_LOCK = threading.Lock()


def names_in(turn) -> tuple[str, ...]:
    out = []
    for step in turn.steps:
        for b in step.result.get("bookings", []) if isinstance(step.result, dict) else []:
            if b.get("guest_name"):
                out.append(b["guest_name"])
    return tuple(out)


def record(turn, session_id: str) -> dict:
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "session_id": session_id,
        "role": turn.role,
        "question": turn.question,
        "answer": turn.answer,
        "tool_calls": [
            {"tool": s.name.removeprefix("MCP call: "), "args": s.input}
            for s in turn.steps
            if s.name.startswith("MCP call")
        ],
        "sources": turn.sources,
        "stop": turn.stop,
        "seconds": round(turn.seconds, 3),
        "tokens_in": turn.usage["input_tokens"],
        "tokens_out": turn.usage["output_tokens"],
        "cost_usd": round(limits.cost_usd(turn.usage), 6),
    }


def write(turn, session_id: str, log_dir: Path | None = None) -> dict:
    clean = scrub(record(turn, session_id), names_in(turn))
    path = Path(log_dir or config.LOG_DIR) / f"requests-{date.today().isoformat()}.jsonl"
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")
    return clean
