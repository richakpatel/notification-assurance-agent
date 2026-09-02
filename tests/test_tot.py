"""Tests for the Tree-of-Thought root-cause engine and the four-agent pipeline.

The ToT layer is ADDITIVE: it attaches a root cause to the ambiguous tail without
changing the deterministic reconciliation counts. These tests check both the
search verdicts and that the pipeline preserves the reconciliation outcome.

Runs with either:
    python3 tests/test_tot.py                 (no dependencies)
    pytest tests/                             (if pytest is installed)

All data is synthetic.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from notification_agent import (
    MAS,
    THRESHOLD,
    NotificationAssuranceAgent,
    Record,
    investigate,
)

CYCLE_START = "2026-10-01"


def test_confirmed_bounce_has_single_root_cause():
    """A stamped-but-bounced record must confirm exactly 'stamped_but_bounced'."""
    r = Record("B1", subscribed_statement=True, last_statement_notified="2026-10-02",
               _actually_delivered=False)
    rc = investigate("stamped_but_bounced", r, MAS, r._actually_delivered, CYCLE_START)
    assert rc.cause == "stamped_but_bounced", rc.cause
    assert rc.verdict == "confirmed", rc.verdict
    assert rc.confidence > 0.9, rc.confidence


def test_confirmed_threshold_silent_failure():
    """Delivered but the crossed tier is missing from the stamp -> silent failure."""
    r = Record("T1", subscribed_thresholds=[80, 90, 100], usage_percentage=85,
               thresholds_notified=[], _actually_delivered=True)
    rc = investigate("threshold_silent_failure", r, THRESHOLD,
                     r._actually_delivered, "2026-10-05")
    assert rc.cause == "threshold_silent_failure", rc.cause
    assert rc.verdict == "confirmed", rc.verdict
    assert rc.escalate_to_human is True


def test_ambiguous_miss_routes_to_human_review():
    """An unstamped miss with unverified delivery is genuinely ambiguous -> review."""
    r = Record("A1", subscribed_statement=True, last_statement_notified=None,
               _actually_delivered=None)
    rc = investigate("eligible_not_stamped", r, MAS, r._actually_delivered, CYCLE_START)
    assert rc.verdict == "plausible", rc.verdict
    assert rc.escalate_to_human is True
    # No candidate was confirmed, so the beam kept more than one live cause.
    assert len(rc.ranked) >= 2, rc.ranked


def test_trajectory_shows_bfs_structure():
    """The ToT trajectory must record the propose/corroborate/decide levels."""
    r = Record("B2", subscribed_statement=True, last_statement_notified="2026-10-02",
               _actually_delivered=False)
    rc = investigate("stamped_but_bounced", r, MAS, r._actually_delivered, CYCLE_START)
    joined = "\n".join(rc.trajectory)
    assert "d1 propose categories" in joined
    assert "d2 " in joined
    assert "d3 decide" in joined
    assert "[pruned]" in joined      # at least one refuted branch was pruned


def test_pipeline_preserves_reconciliation_counts():
    """The Investigator is additive: missed counts must be unchanged, and the
    ambiguous tail must carry a root cause."""
    recs = [
        Record("C002", subscribed_statement=True, last_statement_notified=None),
        Record("C004", subscribed_statement=True, last_statement_notified="2026-10-02",
               _actually_delivered=False),
    ]
    report = NotificationAssuranceAgent().run_cycle(MAS, "2026-10", CYCLE_START, recs)
    assert "C002" in report.result.missed_ids
    tail = [f for f in report.findings if f.root_cause is not None]
    assert tail, "expected the ambiguous tail to carry a ToT root cause"
    # Every needs_review finding was investigated.
    for f in report.findings:
        if f.category == "needs_review":
            assert f.root_cause is not None, f.record_id


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
