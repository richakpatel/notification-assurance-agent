"""Regression test: the agent must match ground truth on the labeled corpus.

Wraps scripts/validate_agent.py so the whole synthetic validation run is a test.
It generates the labeled synthetic corpus, runs the agent across all three
processes, and asserts perfect precision/recall (zero false positives, zero
misses) on both missed-detection and gap-detection.

Runs with either:
    python3 tests/test_validation_corpus.py   (no dependencies)
    pytest tests/                             (if pytest is installed)

All data is synthetic.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from notification_agent import NotificationAssuranceAgent, generate_synthetic_corpus

GAP_KINDS = {"stamped_but_bounced", "threshold_silent_failure"}
CYCLE_START = "2026-09-01"
PERIOD = "2026-09"


def _run():
    """Score the agent on the labeled corpus; return confusion + mismatches."""
    agent = NotificationAssuranceAgent()
    corpus = generate_synthetic_corpus()

    by_type: dict[str, list] = {}
    for lr in corpus:
        by_type.setdefault(lr.notification_type, []).append(lr)

    mismatches: list[str] = []
    m_tp = m_fp = m_fn = 0
    g_tp = g_fp = g_fn = 0

    for nt, labeled in by_type.items():
        report = agent.run_cycle(nt, PERIOD, CYCLE_START, [lr.record for lr in labeled])
        agent_missed = set(report.result.missed_ids)
        agent_gap = {f.record_id: f.observed for f in report.findings if f.observed in GAP_KINDS}

        for lr in labeled:
            rid = lr.record.record_id
            got_missed = rid in agent_missed
            if lr.expected_missed and got_missed:
                m_tp += 1
            elif lr.expected_missed and not got_missed:
                m_fn += 1
                mismatches.append(f"[{nt}] {rid}: expected MISSED ({lr.note})")
            elif (not lr.expected_missed) and got_missed:
                m_fp += 1
                mismatches.append(f"[{nt}] {rid}: false-positive missed ({lr.note})")

            got_gap = agent_gap.get(rid)
            if lr.expected_gap:
                if got_gap == lr.expected_gap:
                    g_tp += 1
                else:
                    g_fn += 1
                    mismatches.append(f"[{nt}] {rid}: expected gap {lr.expected_gap}, got {got_gap}")
            elif got_gap:
                g_fp += 1
                mismatches.append(f"[{nt}] {rid}: unexpected gap {got_gap} ({lr.note})")

    return (m_tp, m_fp, m_fn), (g_tp, g_fp, g_fn), mismatches


def test_corpus_has_all_case_types():
    """The corpus must exercise every seeded case, not just clean sends."""
    corpus = generate_synthetic_corpus()
    assert len(corpus) == 600, len(corpus)
    assert any(lr.expected_missed for lr in corpus)
    assert any(lr.expected_gap == "stamped_but_bounced" for lr in corpus)
    assert any(lr.expected_gap == "threshold_silent_failure" for lr in corpus)


def test_missed_detection_is_perfect():
    """No missed record slips through and no clean record is falsely flagged."""
    (m_tp, m_fp, m_fn), _, mismatches = _run()
    assert m_fp == 0, f"false positives: {[m for m in mismatches if 'false-positive' in m]}"
    assert m_fn == 0, f"misses: {[m for m in mismatches if 'expected MISSED' in m]}"
    assert m_tp > 0, "corpus produced no missed records to detect"


def test_gap_detection_is_perfect():
    """Every seeded observability gap is surfaced, none invented."""
    _, (g_tp, g_fp, g_fn), mismatches = _run()
    assert g_fp == 0, f"invented gaps: {[m for m in mismatches if 'unexpected gap' in m]}"
    assert g_fn == 0, f"missed gaps: {[m for m in mismatches if 'expected gap' in m]}"
    assert g_tp > 0, "corpus produced no gaps to detect"


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
