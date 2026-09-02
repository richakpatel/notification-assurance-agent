"""
Deterministic reconciliation for the Customer Notification Assurance Agent.

This is the NON-RAG half of the hybrid design. It mirrors the real notification
processes' eligibility rules (anonymized) and reconciles, for a given cycle:

    ELIGIBLE-this-cycle   vs.   STAMPED-this-cycle

There is no separate delivery log in the source system -- the stamp field IS the
proof-of-send -- so a record that is eligible but NOT stamped after the run window
is a missed notification. This exactness (set logic over structured records) is why
this half does not use semantic retrieval.

Eligibility predicates below are anonymized restatements of the real query logic:
  - MAS:       active/ended<=45d, subscribed to statements, started <= last month,
               not suppressed for MAS, and NOT already stamped THIS cycle (month).
  - MCN:       active, subscribed to multiplier, a multiplier is effective soon,
               and last multiplier stamp is NULL or older than the throttle window.
  - THRESHOLD: subscribed to a tier the usage has crossed, and that tier is NOT
               already present in the stamped tier list.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MAS, MCN, THRESHOLD, Record


# Anonymized config mirroring the real constants.
MAS_ENDED_GRACE_DAYS = 45
MCN_THROTTLE_DAYS = 80          # "LAST_MULTIPLIER_NOTIFICATION_DAYS_CHECK"
THRESHOLD_TIERS = (80, 90, 100)


@dataclass
class Gap:
    record_id: str
    notification_type: str
    kind: str                 # "eligible_not_stamped" | "stamped_not_eligible" | ...
    detail: str


@dataclass
class ReconciliationResult:
    notification_type: str
    period: str               # e.g. "2024-10" (month) or "2024-10-05" (day)
    eligible_ids: list[str]
    stamped_ids: list[str]    # eligible-set members that ARE stamped for this cycle
    missed_ids: list[str]     # eligible but NOT stamped -> the core gap
    gaps: list[Gap]

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_ids)

    @property
    def delivered_count(self) -> int:
        return len(self.stamped_ids)

    @property
    def missed_count(self) -> int:
        return len(self.missed_ids)


# --- per-process eligibility predicates (anonymized real logic) --------------

def _eligible_mas(r: Record) -> bool:
    active_ok = r.status == "active" or (
        r.ended_days_ago is not None and r.ended_days_ago <= MAS_ENDED_GRACE_DAYS)
    return (
        active_ok
        and r.subscribed_statement
        and r.start_before_last_month
        and MAS not in r.suppressed_types
    )


def _eligible_mcn(r: Record) -> bool:
    return (
        r.status == "active"
        and r.subscribed_multiplier
        and r.multiplier_effective_soon
        and MCN not in r.suppressed_types
    )


def _highest_crossed_tier(r: Record) -> int | None:
    """Highest subscribed tier the usage has crossed (mirrors the real selection logic)."""
    crossed = [t for t in sorted(r.subscribed_thresholds)
               if t in THRESHOLD_TIERS and r.usage_percentage >= t]
    return crossed[-1] if crossed else None


# --- stamped-this-cycle checks (the real "already sent" guards) --------------

def _stamped_mas(r: Record, period_month: str) -> bool:
    # real guard: statement-stamp date is set AND falls in the current month
    return (r.last_statement_notified or "").startswith(period_month)


def _days_between(iso_a: str, iso_b: str) -> int:
    """Whole days from iso_b to iso_a (both YYYY-MM-DD), via the proleptic calendar.
    Avoids importing datetime (Date.now is unavailable in some sandboxes anyway)."""
    def ordinal(iso: str) -> int:
        y, m, d = (int(x) for x in iso.split("-"))
        # days-from-civil (Howard Hinnant's algorithm)
        y2 = y - (m <= 2)
        era = (y2 if y2 >= 0 else y2 - 399) // 400
        yoe = y2 - era * 400
        doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
        doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
        return era * 146097 + doe - 719468
    return ordinal(iso_a) - ordinal(iso_b)


def _stamped_mcn(r: Record, cycle_start: str) -> bool:
    # Real rule: eligible if stamp is NULL or older than the throttle window.
    # So "throttled/already-notified" (skip) == stamped AND newer than the window,
    # i.e. the stamp is fewer than THROTTLE_DAYS before the cycle start.
    if r.last_multiplier_notified is None:
        return False
    age_days = _days_between(cycle_start, r.last_multiplier_notified)
    return age_days < MCN_THROTTLE_DAYS


def _stamped_threshold(r: Record) -> bool:
    tier = _highest_crossed_tier(r)
    # real guard: the sent-tier list excludes that tier -> stamped means it includes it
    return tier is not None and tier in r.thresholds_notified


def reconcile(notification_type: str, period: str, cycle_start: str,
              records: list[Record]) -> ReconciliationResult:
    """Eligible-this-cycle vs. stamped-this-cycle for one process."""
    eligible: list[str] = []
    stamped: list[str] = []
    missed: list[str] = []
    gaps: list[Gap] = []

    for r in records:
        if notification_type == MAS:
            is_elig = _eligible_mas(r)
            is_stamped = _stamped_mas(r, period)
        elif notification_type == MCN:
            is_elig = _eligible_mcn(r)
            is_stamped = _stamped_mcn(r, cycle_start)
        elif notification_type == THRESHOLD:
            is_elig = _highest_crossed_tier(r) is not None and \
                THRESHOLD not in r.suppressed_types
            is_stamped = _stamped_threshold(r)
        else:
            raise ValueError(f"unknown notification_type {notification_type}")

        if is_elig:
            eligible.append(r.record_id)
            if is_stamped:
                stamped.append(r.record_id)
            else:
                missed.append(r.record_id)
                gaps.append(Gap(r.record_id, notification_type,
                                "eligible_not_stamped",
                                "eligible this cycle but no proof-of-send stamp"))
        elif is_stamped:
            # Stamped but not eligible this cycle -> unexpected; worth a look.
            gaps.append(Gap(r.record_id, notification_type,
                            "stamped_not_eligible",
                            "stamped this cycle but not in eligible set"))

    return ReconciliationResult(
        notification_type=notification_type, period=period,
        eligible_ids=eligible, stamped_ids=stamped, missed_ids=missed, gaps=gaps)
