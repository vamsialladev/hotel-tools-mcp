import pytest

from hotel_tools.audit import AuditLog
from hotel_tools.auth import Principal
from hotel_tools.config import DATA_DIR
from hotel_tools.policy.ingest import build_index
from hotel_tools.ratelimit import RateLimiter
from hotel_tools.store import Store
from hotel_tools.tools import Context

SUBJECTS = {"guest": "elena.ruiz@mail.test", "front_desk": "fd-1", "manager": "mgr-1", "auditor": "aud-1"}


@pytest.fixture(scope="session", autouse=True)
def index():
    build_index(use_embeddings=False)


@pytest.fixture
def make_ctx(tmp_path):
    """make_ctx(role, tenant="hg-demo", subject=None, limit=1000): a context with its own empty runtime folder.
    Contexts made in one test share that folder (one installation), like several clients of one server."""
    retriever = {}

    def make(role, tenant="hg-demo", subject=None, limit=1000, clock=None):
        principal = Principal(role, tenant, subject or SUBJECTS[role])
        limiter = RateLimiter({role: limit}, 60.0, clock) if clock else RateLimiter({role: limit})
        ctx = Context(principal, Store(DATA_DIR, tmp_path), AuditLog(tmp_path / "audit.jsonl"), limiter)
        ctx.retriever = retriever.get("r")
        return ctx

    return make


@pytest.fixture(autouse=True)
def fresh_gate_counters():
    """The Admin lockout counts per process (hotel-ai-platform admin_gate): reset it between tests."""
    from hotelplatform import admin_gate

    admin_gate.reset_process_counters()
    yield
    admin_gate.reset_process_counters()


@pytest.fixture(autouse=True)
def ops_log_in_tmp(tmp_path, monkeypatch):
    """The web demo's ops store writes JSONL files without DATABASE_URL; tests write to a temp folder instead."""
    from hotelplatform import oplog

    from hotel_tools.demo import ops

    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = oplog.OpsStore("hotel-tools-mcp", url="", log_dir=tmp_path / "ops")
    monkeypatch.setattr(ops, "store", lambda: store)
    yield store
