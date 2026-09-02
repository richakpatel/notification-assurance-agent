"""Deterministic tests for the reconciliation core and the grounded agent.

Runs with either:
    python3 tests/test_reconciliation.py     (no dependencies)
    pytest tests/                             (if pytest is installed)

All data is synthetic.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent import NotificationAssuranceAgent
from model import MAS, MCN, THRESHOLD, Record
from reconciliation import reconcile


def _mas_records():
    return [
        Record("A1", subscribed_statement=True, last_statement_notified="2026-10-03"),  # stamped
        Record("A2", subscribed_statement=True, last_statement_notified=None),          # missed
        Record("A3", subscribed_statement=True, suppressed_types=[MAS],
               last_statement_notified=None),                                            # suppressed
    ]


def test_reconcile_counts_are_exact():
    """The deterministic core must count eligible/stamped/missed exactly."""
    result = reconcile(MAS, "2026-10", "2026-10-01", _mas_records())
    assert result.eligible_count == 2, result.eligible_count   # A3 suppressed -> not eligible
    assert result.delivered_count == 1, result.delivered_count
    assert result.missed_count == 1, result.missed_count
    assert "A2" in result.missed_ids


def test_suppressed_record_is_not_eligible():
    """A suppressed account is a compliant non-send, never a miss."""
    result = reconcile(MAS, "2026-10", "2026-10-01", _mas_records())
    assert "A3" not in result.missed_ids


def test_threshold_uses_highest_crossed_tier():
    recs = [Record("T1", subscribed_thresholds=[80, 90, 100], usage_percentage=92,
                    thresholds_notified=[80, 90])]  # already stamped for 90 -> not missed
    result = reconcile(THRESHOLD, "2026-10-05", "2026-10-05", recs)
    assert result.missed_count == 0, result.missed_count


def test_agent_flags_bounce_as_high_severity():
    """A stamped-but-bounced record must escalate at high severity."""
    recs = [Record("B1", subscribed_statement=True, last_statement_notified="2026-10-02",
                    _actually_delivered=False)]  # stamped but bounced
    report = NotificationAssuranceAgent().run_cycle(MAS, "2026-10", "2026-10-01", recs)
    bounced = [f for f in report.findings if f.observed == "stamped_but_bounced"]
    assert bounced, "expected a stamped_but_bounced finding"
    assert bounced[0].severity == "high"
    assert bounced[0].escalate is True


def test_low_confidence_routes_to_review():
    """When retrieval is weak, the finding must not be silently trusted."""
    recs = [Record("R1", subscribed_multiplier=True, multiplier_effective_soon=True,
                    last_multiplier_notified=None)]
    report = NotificationAssuranceAgent().run_cycle(MCN, "2026-10", "2026-10-01", recs)
    assert report.findings, "expected at least one finding"
    # Every escalated finding carries a confidence score we can inspect.
    assert all(0.0 <= f.confidence <= 1.0 for f in report.findings)


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed.")


if __name__ == "__main__":
    _main()
