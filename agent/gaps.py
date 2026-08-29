"""
Observability-gap detection for the Customer Notification Assurance Agent.

This module surfaces the failure modes the real source system CANNOT see today,
because there is no delivery-log object and one process swallows its errors:

  G1 "stamped_but_bounced": the record is stamped as sent, but an external
      email-provider probe shows the message actually bounced/was not delivered.
      Invisible to the source system (stamp == only proof-of-send).

  G2 "threshold_silent_failure": for THRESHOLD, the stamp update is only
      System.debug'd on failure -- no gack, no error log. So the usage crossed a
      tier and an email likely went out, yet the tier is missing from the stamp
      list. Looks "missed" but is really a lost proof-of-send.

  G3 "sent_without_stamp_confirmation": delivered externally but no stamp -- the
      inverse integrity mismatch.

The email-provider probe is simulated here via Record._actually_delivered. In a
real deployment this would be an external tool call to the email/event provider
(the grounding source the org lacks internally).
"""

from __future__ import annotations

from dataclasses import dataclass

from model import STAMP_FIELD, THRESHOLD, Record
from reconciliation import ReconciliationResult, _highest_crossed_tier


@dataclass
class ObservabilityGap:
    record_id: str
    notification_type: str
    kind: str
    severity: str            # "high" | "medium"
    detail: str


def _is_stamped_for(nt: str, r: Record, period: str, cycle_start: str) -> bool:
    if nt == THRESHOLD:
        tier = _highest_crossed_tier(r)
        return tier is not None and tier in r.thresholds_notified
    field_name = STAMP_FIELD[nt]
    val = getattr(r, field_name)
    if nt == "MAS":
        return (val or "").startswith(period)
    return val is not None and val >= cycle_start


def probe_email_provider(record_id: str, records: list[Record]) -> bool | None:
    """Simulated external delivery probe. Returns True/False if known, else None.

    Real deployment: an external tool call to the email/event provider. This is the
    grounding source the org does not keep internally.
    """
    for r in records:
        if r.record_id == record_id:
            return r._actually_delivered
    return None


def detect_gaps(result: ReconciliationResult, records: list[Record],
                cycle_start: str) -> list[ObservabilityGap]:
    nt = result.notification_type
    by_id = {r.record_id: r for r in records}
    gaps: list[ObservabilityGap] = []

    # G1: stamped-but-bounced -- probe the external provider for stamped records.
    for rid in result.stamped_ids:
        delivered = probe_email_provider(rid, records)
        if delivered is False:
            gaps.append(ObservabilityGap(
                rid, nt, "stamped_but_bounced", "high",
                "record stamped as sent, but external probe shows bounce/non-delivery"))

    # G2 + G3: reason about missed records against the external probe.
    for rid in result.missed_ids:
        delivered = probe_email_provider(rid, records)
        r = by_id[rid]
        if delivered is True:
            # An email went out but no stamp exists.
            if nt == THRESHOLD:
                gaps.append(ObservabilityGap(
                    rid, nt, "threshold_silent_failure", "high",
                    "usage crossed a tier and email delivered, but tier missing from "
                    "stamp list -- threshold update failure is only logged to debug"))
            else:
                gaps.append(ObservabilityGap(
                    rid, nt, "sent_without_stamp_confirmation", "medium",
                    "delivered externally but no proof-of-send stamp recorded"))
    return gaps
