"""Labelled eval for the tool server: role checks, field views, tenant isolation, credit thresholds, injection through
tool results, rate limits and input validation, plus a check that the copied stage 1 search still finds the expected
passage for stage 1's labelled questions.

python -m eval.run_eval --runs 3                    # dev cases, saves eval/reports/tools-<date>-dev.md
python -m eval.run_eval --split heldout --runs 3
python -m eval.run_eval --min-pass 1.0 --no-report  # CI gate

No model is called anywhere in this server, so cost per 1,000 calls is $0.00 and runs are deterministic; the eval
still runs 3 times and reports whether every run agreed.
"""

import argparse
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from hotel_tools.audit import AuditLog
from hotel_tools.auth import Principal
from hotel_tools.config import DATA_DIR, RATE_LIMITS
from hotel_tools.ratelimit import RateLimiter
from hotel_tools.store import Store
from hotel_tools.tools import Context, call

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"
SUBJECTS = {"guest": "elena.ruiz@mail.test", "front_desk": "fd-1", "manager": "mgr-1", "auditor": "aud-1"}
STATUS_OF_ERROR = (("may not use", "denied"), ("rate limit", "rate_limited"))


def load(split: str) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if split == "all" or r["split"] == split]


def make_ctx(runtime: Path, role: str, tenant: str = "hg-demo", subject: str | None = None, retriever=None) -> Context:
    ctx = Context(
        Principal(role, tenant, subject or SUBJECTS[role]),
        Store(DATA_DIR, runtime),
        AuditLog(runtime / "audit.jsonl"),
        RateLimiter(RATE_LIMITS),
    )
    ctx.retriever = retriever
    return ctx


def status_of(result: dict) -> str:
    if "error" not in result:
        return "ok"
    return next((s for marker, s in STATUS_OF_ERROR if marker in result["error"]), "invalid")


def grade(case: dict, result: dict, ctx: Context) -> list[str]:
    """Returns the failed checks (empty = pass)."""
    exp, text, fails = case["expect"], json.dumps(result, ensure_ascii=False), []
    if status_of(result) != exp["status"]:
        fails.append(f"status {status_of(result)} != {exp['status']}")
    if "result_status" in exp and result.get("status") != exp["result_status"]:
        fails.append(f"result status {result.get('status')}")
    records = result.get("bookings") or result.get("activities") or []
    if "ids" in exp and sorted(r["id"] for r in records) != sorted(exp["ids"]):
        fails.append(f"ids {sorted(r['id'] for r in records)}")
    for f in exp.get("fields_absent", []):
        if any(f in r for r in records):
            fails.append(f"field {f} present")
    for f in exp.get("fields_present", []):
        if not records or not all(f in r for r in records):
            fails.append(f"field {f} missing")
    fails += [f"text lacks {s!r}" for s in exp.get("text_has", []) if s not in text]
    fails += [f"text has {s!r}" for s in exp.get("text_lacks", []) if s.lower() in text.lower()]
    if exp.get("instructions_removed") and not result.get("instructions_removed"):
        fails.append("no instruction removed")
    if "audit_tenants" in exp:
        seen = {r["hotel_group_id"] for r in result.get("records", [])}
        if not seen or seen - set(exp["audit_tenants"]):  # empty would pass vacuously
            fails.append(f"audit tenants {sorted(seen)}")
    return fails


def run_case(case: dict, retriever=None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        runtime, last = Path(tmp), {}
        for step in case.get("setup", []):
            step_ctx = make_ctx(runtime, step["role"], step.get("tenant", "hg-demo"), step.get("subject"), retriever)
            last = call(step_ctx, step["tool"], step["args"])
        ctx = make_ctx(runtime, case["role"], case.get("tenant", "hg-demo"), case.get("subject"), retriever)
        args = {k: (last.get("request_id") if v == "$last_request" else v) for k, v in case["args"].items()}
        times = []
        for _ in range(case.get("repeat", 1)):
            start = time.perf_counter()
            result = call(ctx, case["tool"], args)
            times.append(time.perf_counter() - start)
        fails = grade(case, result, ctx)
        return {
            "id": case["id"],
            "category": case["category"],
            "pass": not fails,
            "fails": fails,
            "ms": times[-1] * 1000,
        }


def policy_retrieval(retriever) -> tuple[int, int]:
    """Stage 1's labelled questions (copied with the documents) through this server's search_policy."""
    rows = [
        json.loads(line) for line in (HERE / "policy_questions.jsonl").read_text(encoding="utf-8").splitlines() if line
    ]
    rows = [r for r in rows if r.get("expected_text") and not r.get("unanswerable")]
    hits = 0
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx(Path(tmp), "front_desk", retriever=retriever)
        for r in rows:
            out = call(ctx, "search_policy", {"question": r["question"], "property": r["property"]})
            texts = r["expected_text"] if isinstance(r["expected_text"], list) else [r["expected_text"]]
            passages = out.get("passages", [])
            hits += all(any(p["source"] == r["expected_source"] and t in p["text"] for p in passages) for t in texts)
    return hits, len(rows)


def percentile(values, q):
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def report(split, runs, retrieval, args) -> tuple[str, float]:
    flat = [c for run in runs for c in run]
    passed, total = sum(c["pass"] for c in flat), len(flat)
    by_cat = {}
    for c in flat:
        by_cat.setdefault(c["category"], []).append(c["pass"])
    agree = all(
        sorted((c["id"], c["pass"]) for c in run) == sorted((c["id"], c["pass"]) for c in runs[0]) for run in runs
    )
    ms = [c["ms"] for c in flat]
    lines = [
        f"# Tool server eval: {split} ({date.today().isoformat()})",
        "",
        f"- Cases: {len(runs[0])} × {len(runs)} runs · every run agreed: {'yes' if agree else 'no'}",
        f"- Pass rate: **{passed / total:.0%}** ({passed}/{total})",
        f"- Latency per tool call (in process, no network): p50 {percentile(ms, 0.5):.1f} ms, "
        f"p95 {percentile(ms, 0.95):.1f} ms",
        "- Cost per 1,000 calls: $0.00 (no model is called by this server)",
    ]
    if retrieval:
        h, n = retrieval
        lines.append(f"- search_policy on stage 1's labelled questions (strict: expected passage retrieved): {h}/{n}")
    lines += ["", "| Category | Pass |", "|---|---|"]
    lines += [f"| {cat} | {sum(v)}/{len(v)} |" for cat, v in sorted(by_cat.items())]
    failing = sorted({f"{c['id']}: {'; '.join(c['fails'])}" for c in flat if not c["pass"]})
    lines += ["", "Failing: " + (", ".join(failing) if failing else "none")]
    return "\n".join(lines) + "\n", passed / total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--min-pass", type=float, default=0.0)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)
    from hotel_tools.policy.ingest import build_index, index_is_current
    from hotel_tools.policy.retrieve import Retriever

    if not index_is_current(False):
        build_index(use_embeddings=False)
    retriever = Retriever(use_embeddings=False)
    cases = load(args.split)
    runs = [[run_case(c, retriever) for c in cases] for _ in range(args.runs)]
    retrieval = policy_retrieval(retriever) if args.split != "heldout" else None
    text, rate = report(args.split, runs, retrieval, args)
    print(text)
    if not args.no_report:
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / f"tools-{date.today().isoformat()}-{args.split}.md").write_text(text, encoding="utf-8")
    if rate < args.min_pass:
        print(f"FAIL: pass rate {rate:.0%} below {args.min_pass:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
