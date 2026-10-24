"""Synthetic bookings and activities (read-only) and the requests the tools create (append-only JSONL).

Every record carries `hotel_group_id`, and every read takes the caller's tenant: there is no method that reads across
tenants. A record of another tenant looks exactly like a record that doesn't exist.
"""

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


class Store:
    def __init__(self, data_dir: Path, runtime_dir: Path, clock=lambda: datetime.now(UTC)):
        self.tenants = json.loads((data_dir / "tenants.json").read_text(encoding="utf-8"))
        self.bookings = json.loads((data_dir / "bookings.json").read_text(encoding="utf-8"))
        self.activities = json.loads((data_dir / "activities.json").read_text(encoding="utf-8"))
        self.requests_file = runtime_dir / "requests.jsonl"
        self.clock, self.lock = clock, threading.Lock()

    def properties(self, tenant: str) -> list[str]:
        return list(self.tenants.get(tenant, {}).get("properties", []))

    def booking(self, tenant: str, booking_id: str) -> dict | None:
        bid = (booking_id or "").strip().upper()
        return next((b for b in self.bookings if b["hotel_group_id"] == tenant and b["id"] == bid), None)

    def bookings_for(self, tenant: str, email: str) -> list[dict]:
        email = email.lower()
        return [b for b in self.bookings if b["hotel_group_id"] == tenant and b["guest_email"].lower() == email]

    def activities_for(self, tenant: str, prop: str) -> list[dict]:
        return [a for a in self.activities if a["hotel_group_id"] == tenant and a["property"] == prop]

    # ---------- requests (append-only; the latest record for an id wins) ----------
    def _all_requests(self) -> list[dict]:
        if not self.requests_file.exists():
            return []
        lines = self.requests_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def requests(self, tenant: str) -> dict:
        latest = {}
        for r in self._all_requests():
            if r["hotel_group_id"] == tenant:
                latest[r["id"]] = r
        return latest

    def append_request(self, tenant: str, record: dict) -> dict:
        record = {
            "id": record.get("id") or f"REQ-{uuid.uuid4().hex[:8].upper()}",
            "at": self.clock().isoformat(timespec="seconds"),
            **{k: v for k, v in record.items() if k not in ("id", "hotel_group_id")},
            "hotel_group_id": tenant,  # always the caller's tenant, whatever the record says
        }
        with self.lock:
            self.requests_file.parent.mkdir(parents=True, exist_ok=True)
            with self.requests_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
