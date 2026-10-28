"""Red-team suite for the MCP server and its web demo: the shared corpus (hotel-ai-platform) plus this repo's own
cases (redteam/cases.jsonl), through the real defences. No API calls; runs in CI.

    python scripts/run_redteam.py                 print the summary, exit 1 on any new miss
    python scripts/run_redteam.py --report        also rewrite docs/redteam-report.md

Layers:
    input      a visitor's question to the web demo -> the shared input check (src/hotel_tools/demo/ops.py)
    output     an answer -> the shared output check, grounded on the turn's MCP results
    retrieved  a policy passage or booking note -> the server's quarantine (src/hotel_tools/guard.py)
    tool       an MCP call as a role -> the real server through an in-process MCP client (RBAC, field views,
               tenant isolation, credit limits)
"""

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hotelplatform import jsonlog, redteam  # noqa: E402

from hotel_tools import guard  # noqa: E402
from hotel_tools.audit import AuditLog  # noqa: E402
from hotel_tools.auth import Principal  # noqa: E402
from hotel_tools.config import DATA_DIR  # noqa: E402
from hotel_tools.demo import agent, ops  # noqa: E402
from hotel_tools.ratelimit import RateLimiter  # noqa: E402
from hotel_tools.store import Store  # noqa: E402
from hotel_tools.tools import Context  # noqa: E402

CASES = ROOT / "redteam" / "cases.jsonl"
OVERRIDES = ROOT / "redteam" / "overrides.json"
REPORT = ROOT / "docs" / "redteam-report.md"
SUBJECTS = {"guest": "elena.ruiz@mail.test", "front_desk": "fd-1", "manager": "mgr-1", "auditor": "aud-1"}


def input_layer(case):
    v = ops.check_question(case.text)
    if not v.allowed:
        return redteam.Outcome("block", v.reason, ", ".join(v.reasons))
    if any(f.startswith("injection_removed") for f in v.flags):
        return redteam.Outcome("quarantine", None, v.text[:100])
    if any(f.startswith("pii_redacted") for f in v.flags):
        return redteam.Outcome("redact")
    return redteam.Outcome("allow")


def output_layer(case):
    v = ops.check_answer(case.text, case.context.get("sources", []), case.context.get("input", ""))
    if not v.allowed:
        return redteam.Outcome("block", v.reason)
    return redteam.Outcome("redact" if v.text != case.text else "allow", None, ", ".join(v.flags))


def retrieved_layer(case):
    _, removed = guard.quarantine(case.text)
    return redteam.Outcome("quarantine" if removed else "allow")


class Servers:
    """One in-process MCP server per role, sharing one runtime folder (one installation)."""

    def __init__(self, folder: Path):
        self.folder, self.sessions = folder, {}

    def call(self, role: str, tool: str, args: dict) -> dict:
        if role not in self.sessions:
            ctx = Context(Principal(role, "hg-demo", SUBJECTS[role]), Store(DATA_DIR, self.folder),
                          AuditLog(self.folder / "audit.jsonl"), RateLimiter({role: 1000}))  # fmt: skip
            self.sessions[role] = agent.McpSession(ctx)
        session = self.sessions[role]
        if tool not in {t["name"] for t in session.tools}:
            return {"error": f"{tool} is not available to the {role} role"}
        return session.call(tool, args)

    def close(self):
        for s in self.sessions.values():
            s.close()


def tool_layer_for(servers: Servers):
    def tool_layer(case):
        spec = json.loads(case.text)
        result = servers.call(spec["role"], spec["tool"], spec["args"])
        text = json.dumps(result)
        # Stopped: refused, or only a request waiting for a manager. Anything else is an action that happened.
        stopped = "error" in result or "manager" in text.lower() and "approv" in text.lower()
        return redteam.Outcome("block" if stopped else "allow", None, text[:100])

    return tool_layer


def shared_cases_for_this_app() -> list:
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))["expect"] if OVERRIDES.exists() else {}
    cases = redteam.shared_cases()
    for c in cases:
        if c.id in overrides:
            c.expect, c.reason = overrides[c.id], None
    return cases


def run():
    jsonlog.configure("redteam", "ci", stream=io.StringIO())
    with tempfile.TemporaryDirectory() as tmp:
        servers = Servers(Path(tmp))
        try:
            handlers = {"input": input_layer, "output": output_layer, "retrieved": retrieved_layer,
                        "tool": tool_layer_for(servers)}  # fmt: skip
            shared = redteam.run(shared_cases_for_this_app(), handlers)
            own = redteam.run(redteam.load_cases(CASES), handlers)
        finally:
            servers.close()
    return shared, own


def known_gaps() -> set[str]:
    lines = (ROOT / "redteam" / "known_gaps.txt").read_text(encoding="utf-8").splitlines()
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    shared, own = run()
    for name, results in (("shared corpus", shared), ("this repo's cases", own)):
        s = redteam.score(results)
        print(f"{name}: {s['passed']}/{s['cases']} passed; attacks stopped {s['attacks_stopped']}/{s['attacks']}; "
              f"false alarms {s['false_alarms']}/{s['controls']}")  # fmt: skip
        for r in results:
            if not r.passed:
                print(f"  FAIL {r.case.id} [{r.case.category}] expected {r.case.expect}, got {r.outcome.verdict}"
                      f"  ({r.outcome.detail[:80]})")  # fmt: skip
    if args.report:
        REPORT.write_text(
            redteam.report_markdown(shared, "Red-team report: shared corpus through the MCP server and web demo")
            + "\n"
            + redteam.report_markdown(own, "Red-team report: this repo's own cases (held out)"),
            encoding="utf-8",
            newline="\n",
        )
    new_failures = [r.case.id for r in shared + own if not r.passed and r.case.id not in known_gaps()]
    if new_failures:
        print("GATE FAILED: new red-team failures:", ", ".join(new_failures))
    return 1 if new_failures else 0


if __name__ == "__main__":
    sys.exit(main())
