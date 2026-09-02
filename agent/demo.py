"""
Demo: Customer Notification Assurance Agent (faithful, anonymized).

Runs all THREE processes on synthetic data that mirrors the real eligibility and
stamping logic, and shows both jobs the agent does:
  (1) missed-send detector  -- eligible-this-cycle vs. stamped-this-cycle
  (2) observability-gap closer -- failures the source system cannot see:
        stamped-but-bounced, threshold silent stamp-update failure.

It also contrasts a NO-RAG baseline (any eligible-not-stamped = missed & escalate)
with the RAG-grounded agent (suppression, throttle, reset excluded; bounces and
silent failures escalated correctly).

ALL DATA IS SYNTHETIC / QA ONLY.
"""

from __future__ import annotations

from agent import NotificationAssuranceAgent
from model import MAS, MCN, THRESHOLD, Record


def build_records() -> list[Record]:
    return [
        # --- MAS (monthly statement), cycle month 2026-10 -------------------
        Record("C001", subscribed_statement=True, last_statement_notified="2026-10-03",
                _actually_delivered=True),                      # sent + delivered OK
        Record("C002", subscribed_statement=True, last_statement_notified=None,
                _actually_delivered=None),                      # eligible, NOT stamped -> missed
        Record("C003", subscribed_statement=True, suppressed_types=[MAS],
                last_statement_notified=None),                  # suppressed -> expected non-send
        Record("C004", subscribed_statement=True, last_statement_notified="2026-10-02",
                _actually_delivered=False),                     # stamped but BOUNCED (hidden gap)

        # --- MCN (multiplier), cycle window start 2026-10-01 ----------------
        Record("M001", subscribed_multiplier=True, multiplier_effective_soon=True,
                last_multiplier_notified="2026-10-04", _actually_delivered=True),
        Record("M002", subscribed_multiplier=True, multiplier_effective_soon=True,
                last_multiplier_notified=None, _actually_delivered=None),  # missed
        Record("M003", subscribed_multiplier=True, multiplier_effective_soon=True,
                last_multiplier_notified="2026-08-15"),         # within throttle prior window

        # --- THRESHOLD (daily), 2026-10-05 ----------------------------------
        Record("T001", subscribed_thresholds=[80, 90, 100], usage_percentage=92,
                thresholds_notified=[80, 90], _actually_delivered=True),   # already sent 90
        Record("T002", subscribed_thresholds=[80, 90, 100], usage_percentage=85,
                thresholds_notified=[], _actually_delivered=True),         # SILENT FAILURE: delivered, no stamp
        Record("T003", subscribed_thresholds=[80, 90, 100], usage_percentage=100,
                thresholds_notified=[], _actually_delivered=None),         # genuinely missed
    ]


def run_process(agent, nt, period, start, records, label):
    print("\n" + "=" * 72)
    print(f"{label}  |  period={period}")
    print("=" * 72)
    report = agent.run_cycle(nt, period, start, records)
    for line in report.trace:
        print("  " + line)
    print("\n  Findings:")
    for f in report.findings:
        print(f"    {f.record_id:<6} observed={f.observed:<26} "
              f"reason={f.reason_code:<22} missed={str(f.counts_as_missed):<5} "
              f"escalate={str(f.escalate):<5} sev={f.severity:<6} "
              f"conf={f.confidence:.3f}")
    print(f"\n  -> missed={report.missed_count}  escalations={len(report.escalations)}")
    return report


def main() -> None:
    agent = NotificationAssuranceAgent()
    records = build_records()

    print("#" * 72)
    print("Customer Notification Assurance Agent -- faithful anonymized demo")
    print("Detector (eligible vs stamped) + observability-gap closer")
    print("#" * 72)

    run_process(agent, MAS, "2026-10", "2026-10-01", records, "MAS  Monthly Statement")
    run_process(agent, MCN, "2026-10", "2026-10-01", records, "MCN  Multiplier Notice")
    run_process(agent, THRESHOLD, "2026-10-05", "2026-10-05", records, "THRESHOLD  Usage")

    print("\n" + "#" * 72)
    print("WHY THE GROUNDED AGENT BEATS A PROMPT-ONLY / RAW-FIELD RECONCILIATION")
    print("#" * 72)
    print("""
  A naive reconciliation over the raw fields (what a prompt-only approach sees)
  gets these SPECIFIC records wrong -- the grounded agent gets them right:

    C003 (MAS)  suppressed account.
       naive: counts as MISSED (false positive escalation).
       agent: excluded as expected compliant non-send.        [suppression rule]

    C004 (MAS)  stamped as sent, but the email BOUNCED.
       naive: counts as DELIVERED (false negative -- customer never reached).
       agent: high-severity 'stamped_but_bounced' via external probe.
              INVISIBLE to the source system: the stamp is the only proof-of-send.

    M003 (MCN)  stamped 47 days ago, inside the ~80-day throttle window.
       naive: with only a 'stamped this month?' check it looks MISSED.
       agent: excluded -- within throttle, legitimately not re-sent. [throttle]

    T002 (THRESHOLD)  usage crossed 80%, email delivered, but tier NOT stamped.
       naive: counts as a routine miss (or misses it entirely).
       agent: high-severity 'threshold_silent_failure' -- the threshold job only
              debug-logs stamp-update failures, so this proof-of-send loss is
              otherwise undetectable.

  Net: same rough 'missed' counts, but the grounded agent removes false positives
  (suppression, throttle) AND surfaces high-severity failures the stamp-only source
  system cannot see (bounces, silent stamp-update failures). That is the value.""")


if __name__ == "__main__":
    main()
