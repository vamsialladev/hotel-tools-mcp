"""The eval runner's checks and the three-roles demo (no model, no keys)."""

import sys

from eval import run_eval
from hotel_tools.config import ROOT


def test_eval_cases_are_labelled_and_split():
    dev, held = run_eval.load("dev"), run_eval.load("heldout")
    assert len(dev) >= 30 and len(held) >= 5
    assert {c["category"] for c in dev} >= {"role_denied", "tenant_isolation", "injection_in_results", "rate_limit"}


def test_every_dev_case_passes():
    results = [run_eval.run_case(c) for c in run_eval.load("dev") if c["tool"] != "search_policy"]
    assert [r["id"] for r in results if not r["pass"]] == []


def test_grade_catches_wrong_results(make_ctx):
    ctx = make_ctx("front_desk")
    case = {"expect": {"status": "ok", "ids": ["X"], "fields_present": ["notes"], "text_has": ["zzz"]}}
    fails = run_eval.grade(case, {"bookings": [{"id": "BR-1042"}]}, ctx)
    assert any(f.startswith("ids") for f in fails) and "field notes missing" in fails and "text lacks 'zzz'" in fails
    empty = run_eval.grade({"expect": {"status": "ok", "audit_tenants": ["hg-demo"]}}, {"records": []}, ctx)
    assert empty == ["audit tenants []"]  # an empty list must not pass
    assert run_eval.status_of({"error": "rate limit: 10 calls"}) == "rate_limited"


def test_report_and_cli(capsys):
    assert run_eval.main(["--split", "heldout", "--no-report", "--min-pass", "1.0"]) == 0
    out = capsys.readouterr().out
    assert "Pass rate: **100%**" in out and "$0.00" in out


def test_demo_shows_the_role_differences():
    sys.path.insert(0, str(ROOT / "scripts"))
    import demo_roles

    rows = {(r, t): o for r, t, o in demo_roles.run()}
    assert rows[("guest", "issue_credit_request")].startswith("refused")
    assert rows[("front_desk", "issue_credit_request")].startswith("pending_manager_approval")
    assert rows[("manager", "issue_credit_request")].startswith("approved")
    assert "chain intact: True" in rows[("auditor", "get_audit_log")]
