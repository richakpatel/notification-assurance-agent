"""
Synthetic data model for the Customer Notification Assurance Agent.

Models a real notification architecture (three processes) with ANONYMIZED field
names and SYNTHETIC data only -- no proprietary field names or real records appear.
The synthetic record below carries the signals each process reads and stamps
(eligibility, subscription, suppression, usage tier, and proof-of-send stamps).

Key real-world fact this model captures: there is NO separate delivery-log object.
The stamp field IS the only proof-of-send. So "delivered this cycle" == "stamped
this cycle", and a truly-bounced-but-stamped email is invisible to the source system.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The three notification processes.
MAS = "MAS"              # monthly account statement
MCN = "MCN"              # multiplier change notice
THRESHOLD = "THRESHOLD"  # daily usage threshold

# Which stamp field each process writes on successful send (synthetic names).
STAMP_FIELD = {
    MAS: "last_statement_notified",       # date
    MCN: "last_multiplier_notified",      # date
    THRESHOLD: "thresholds_notified",     # list of crossed tiers, e.g. [80, 90]
}


@dataclass
class Record:
    """A synthetic contract/entitlement/usage record carrying all signals the
    three processes read and stamp. One flat record keeps the demo readable;
    in the real system these live on separate related objects.
    """
    record_id: str
    status: str = "active"                       # active | ended
    ended_days_ago: int | None = None            # for MAS "ended <=45d" rule
    start_before_last_month: bool = True         # started on/before last month

    # Subscription / recipient signals
    subscribed_statement: bool = False           # subscribed to monthly statements + a valid recipient type
    subscribed_multiplier: bool = False          # subscribed to multiplier-change notices
    subscribed_thresholds: list[int] = field(default_factory=list)  # e.g. [80, 90, 100]

    # Suppression flag
    suppressed_types: list[str] = field(default_factory=list)       # e.g. ["MAS"]

    # Multiplier trigger window (upcoming effective date)
    multiplier_effective_soon: bool = False

    # Current usage tier crossed this cycle
    usage_percentage: int = 0

    # ---- stamp fields (proof-of-send) ------------------------------------
    last_statement_notified: str | None = None   # ISO date
    last_multiplier_notified: str | None = None  # ISO date
    thresholds_notified: list[int] = field(default_factory=list)

    # ---- ground-truth ONLY for the demo's gap-detection ------------------
    # In reality no delivery log exists; we carry a hidden "actually delivered"
    # flag so the demo can show the "stamped but bounced" gap the source system
    # cannot see. The agent does NOT read this except via a simulated external
    # email-provider probe (see gaps.py).
    _actually_delivered: bool | None = None      # None = unknown / not probed
