"""
Validation harness for the Customer Notification Assurance Agent.

Generates a LABELED synthetic corpus (src/notification_agent/synthetic_data.py),
runs the agent across all three processes, and scores its verdicts against ground
truth on two dimensions:

  1. Missed detection  -- did the agent's eligible-vs-stamped reconciliation put
                          exactly the genuinely-missed records in the missed set,
                          with no false positives (suppressed / throttled / clean)?
  2. Gap detection     -- did the agent surface each seeded observability gap
                          (stamped_but_bounced, threshold_silent_failure)?

Prints a per-process + overall scorecard and lists every mismatch. Exits non-zero
if anything is wrong, so it doubles as a regression test.

Run from the repo root:  python3 scripts/validate_agent.py       (no dependencies)
ALL DATA IS SYNTHETIC.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from notification_agent import NotificationAssuranceAgent
from notification_agent.synthetic_data import LabeledRecord, generate

GAP_KINDS = {"stamped_but_bounced", "threshold_silent_failure"}
CYCLE_START = "2026-09-01"
PERIOD = "2026-09"


def _confusion(tp: int, fp: int, fn: int) -> str:
    total = tp + fp + fn
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return f"tp={tp} fp={fp} fn={fn}  precision={prec:.3f} recall={rec:.3f}"


def validate() -> int:
    agent = NotificationAssuranceAgent()
    corpus = generate()

    # Group labeled records by process.
    by_type: dict[str, list[LabeledRecord]] = {}
    for lr in corpus:
        by_type.setdefault(lr.notification_type, []).append(lr)

    mismatches: list[str] = []
    # Running totals across processes.
    m_tp = m_fp = m_fn = 0        # missed-detection confusion
    g_tp = g_fp = g_fn = 0        # gap-detection confusion

    print("#" * 72)
    print("Agent validation on labeled synthetic corpus  (ALL DATA SYNTHETIC)")
    print(f"records: {len(corpus)}  |  cycle: {PERIOD}")
    print("#" * 72)

    for nt, labeled in by_type.items():
        records = [lr.record for lr in labeled]
        report = agent.run_cycle(nt, PERIOD, CYCLE_START, records)

        agent_missed = set(report.result.missed_ids)
        agent_gap = {
            f.record_id: f.observed for f in report.findings if f.observed in GAP_KINDS
        }

        pm_tp = pm_fp = pm_fn = 0
        pg_tp = pg_fp = pg_fn = 0
        for lr in labeled:
            rid = lr.record.record_id

            # --- missed detection ---
            got_missed = rid in agent_missed
            if lr.expected_missed and got_missed:
                pm_tp += 1
            elif lr.expected_missed and not got_missed:
                pm_fn += 1
                mismatches.append(f"[{nt}] {rid}: expected MISSED ({lr.note}) but agent did not flag it")
            elif (not lr.expected_missed) and got_missed:
                pm_fp += 1
                mismatches.append(f"[{nt}] {rid}: false positive -- agent flagged missed ({lr.note})")

            # --- gap detection ---
            got_gap = agent_gap.get(rid)
            if lr.expected_gap:
                if got_gap == lr.expected_gap:
                    pg_tp += 1
                else:
                    pg_fn += 1
                    mismatches.append(
                        f"[{nt}] {rid}: expected gap '{lr.expected_gap}' ({lr.note}) but agent observed '{got_gap}'")
            elif got_gap:
                pg_fp += 1
                mismatches.append(f"[{nt}] {rid}: unexpected gap '{got_gap}' ({lr.note})")

        print(f"\n== {nt} ==  ({len(labeled)} records)")
        print(f"  reconcile: eligible={report.result.eligible_count} "
              f"stamped={report.result.delivered_count} missed={report.result.missed_count}")
        print(f"  missed detection : {_confusion(pm_tp, pm_fp, pm_fn)}")
        print(f"  gap detection    : {_confusion(pg_tp, pg_fp, pg_fn)}")

        m_tp += pm_tp; m_fp += pm_fp; m_fn += pm_fn
        g_tp += pg_tp; g_fp += pg_fp; g_fn += pg_fn

    print("\n" + "=" * 72)
    print("OVERALL")
    print(f"  missed detection : {_confusion(m_tp, m_fp, m_fn)}")
    print(f"  gap detection    : {_confusion(g_tp, g_fp, g_fn)}")
    print("=" * 72)

    if mismatches:
        print(f"\n{len(mismatches)} MISMATCH(ES):")
        for m in mismatches[:40]:
            print("  - " + m)
        if len(mismatches) > 40:
            print(f"  ... and {len(mismatches) - 40} more")
        print("\nRESULT: FAIL")
        return 1

    print("\nRESULT: PASS -- agent matched ground truth on every record.")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
