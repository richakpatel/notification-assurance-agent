"""
Synthetic sample records for the Customer Notification Assurance Agent demo.

These records are hand-built to exercise every teaching case across the three
processes (MAS / MCN / THRESHOLD): a clean send, a genuine miss, a suppressed
account, a stamped-but-bounced gap, a throttled multiplier notice, and a
silent threshold stamp-update failure.

ALL DATA IS SYNTHETIC / QA ONLY. No proprietary field names or real records.
"""

from __future__ import annotations

from .model import MAS, MCN, THRESHOLD, Record


def build_records() -> list[Record]:
    """Return the synthetic record set used by the demo and the test suite."""
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
