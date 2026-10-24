"""Append-only, hash-chained audit log: one record per tool call, written before the result is returned.

Each record holds the tenant, role, a hash of the subject, the tool, a SHA-256 of the canonical arguments (never the
arguments themselves), the result status and a short redacted detail. Each record also stores the previous record's
hash, so editing or deleting a line breaks `verify()`. There is no update or delete method.
"""

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from hotel_tools.policy.pii import scrub_text

STATUSES = ("ok", "denied", "invalid", "rate_limited", "error")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path, clock=lambda: datetime.now(UTC)):
        self.path, self.clock = path, clock
        self.lock = threading.Lock()

    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def record(self, principal, tool: str, args: dict, status: str, detail: str = "") -> dict:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status}")
        with self.lock:
            records = self._records()
            prev = records[-1]["hash"] if records else "0" * 64
            rec = {
                "seq": len(records) + 1,
                "ts": self.clock().isoformat(timespec="seconds"),
                "hotel_group_id": principal.hotel_group_id,
                "role": principal.role,
                "subject": sha(principal.subject)[:12],
                "tool": tool,
                "args_sha256": sha(canonical(args)),
                "status": status,
                "detail": scrub_text(detail)[:200],
                "prev": prev,
            }
            rec["hash"] = sha(canonical(rec))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return rec

    def read(self, hotel_group_id: str, limit: int = 50, tool: str | None = None, status: str | None = None) -> list:
        """Newest first, this tenant only."""
        out = [
            r
            for r in self._records()
            if r["hotel_group_id"] == hotel_group_id
            and (tool is None or r["tool"] == tool)
            and (status is None or r["status"] == status)
        ]
        return list(reversed(out))[: max(0, limit)]

    def verify(self) -> bool:
        prev = "0" * 64
        for rec in self._records():
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev") != prev or sha(canonical(body)) != rec.get("hash"):
                return False
            prev = rec["hash"]
        return True
