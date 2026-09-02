"""
Synthetic validation dataset generator for the Customer Notification Assurance Agent.

Produces a LABELED corpus -- each record paired with the outcome the agent SHOULD
reach -- so the validation harness (scripts/validate_agent.py) can score the agent
against ground truth across all three processes and every edge case.

The population *shape* (category mix, missed rate, per-category volumes) is modeled
on anonymized AGGREGATE ratios observed in real monitoring reports:

    * category mix (contracts):  OEM ~1%,  Other Reseller ~4%,  Direct Customer ~95%
    * completed-cycle outcome:   ~94% received / ~6% missed
    * ~3.2 entitlements per contract

NO real record, id, name, field name, or value is used or reproduced. Only these
aggregate proportions inform the distribution; every record below is fabricated.

Determinism: a fixed seed makes the corpus reproducible so validation is stable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .model import MAS, MCN, THRESHOLD, Record

# ---- population shape (from anonymized aggregate ratios) --------------------
CATEGORY_WEIGHTS = {"OEM": 0.01, "OTHER": 0.04, "DIRECT": 0.95}
BASE_MISSED_RATE = 0.06          # ~6% of eligible end a completed cycle unstamped

# Rates for the "invisible" failure modes the agent exists to catch. These are
# deliberately higher than they'd be in production so the validation corpus
# actually exercises the gap detector; they are illustrative, not measured.
BOUNCE_RATE = 0.03               # stamped but the probe shows a bounce
SILENT_FAIL_RATE = 0.04          # threshold delivered but tier never stamped
SUPPRESSED_RATE = 0.05           # compliant non-send (MAS)
THROTTLE_RATE = 0.10             # MCN skipped inside the 20-day throttle window


@dataclass
class LabeledRecord:
    """A synthetic record plus the ground-truth the agent should reach for it."""
    record: Record
    notification_type: str
    # ground truth:
    expected_missed: bool           # should this count as a missed notification?
    expected_gap: str | None        # 'stamped_but_bounced' | 'threshold_silent_failure' | None
    note: str                       # human-readable label of the case


def _stamp_date(cycle_start: str, within: bool) -> str:
    """A stamp date inside (within=True) or before the current cycle."""
    year, month, _ = cycle_start.split("-")
    if within:
        return f"{year}-{month}-05"
    # a prior-period stamp (previous month)
    pm = int(month) - 1 or 12
    py = int(year) if int(month) > 1 else int(year) - 1
    return f"{py:04d}-{pm:02d}-15"


def _mas_record(rng: random.Random, i: int, cycle_start: str) -> LabeledRecord:
    rid = f"S{i:05d}"
    roll = rng.random()
    if roll < SUPPRESSED_RATE:
        return LabeledRecord(
            Record(rid, subscribed_statement=True, suppressed_types=[MAS],
                   last_statement_notified=None),
            MAS, expected_missed=False, expected_gap=None, note="suppressed (compliant non-send)")
    if roll < SUPPRESSED_RATE + BOUNCE_RATE:
        return LabeledRecord(
            Record(rid, subscribed_statement=True,
                   last_statement_notified=_stamp_date(cycle_start, True),
                   _actually_delivered=False),
            MAS, expected_missed=False, expected_gap="stamped_but_bounced",
            note="stamped but bounced (invisible gap)")
    if roll < SUPPRESSED_RATE + BOUNCE_RATE + BASE_MISSED_RATE:
        return LabeledRecord(
            Record(rid, subscribed_statement=True, last_statement_notified=None,
                   _actually_delivered=None),
            MAS, expected_missed=True, expected_gap=None, note="eligible, not stamped (missed)")
    # clean send
    return LabeledRecord(
        Record(rid, subscribed_statement=True,
               last_statement_notified=_stamp_date(cycle_start, True),
               _actually_delivered=True),
        MAS, expected_missed=False, expected_gap=None, note="clean send")


def _mcn_record(rng: random.Random, i: int, cycle_start: str) -> LabeledRecord:
    rid = f"M{i:05d}"
    roll = rng.random()
    if roll < THROTTLE_RATE:
        # stamped ~10 days ago -> inside the 20-day throttle -> legitimately not re-sent
        return LabeledRecord(
            Record(rid, subscribed_multiplier=True, multiplier_effective_soon=True,
                   last_multiplier_notified=_stamp_date(cycle_start, True)),
            MCN, expected_missed=False, expected_gap=None, note="within throttle window")
    if roll < THROTTLE_RATE + BASE_MISSED_RATE:
        return LabeledRecord(
            Record(rid, subscribed_multiplier=True, multiplier_effective_soon=True,
                   last_multiplier_notified=None, _actually_delivered=None),
            MCN, expected_missed=True, expected_gap=None, note="eligible, not stamped (missed)")
    # clean send
    return LabeledRecord(
        Record(rid, subscribed_multiplier=True, multiplier_effective_soon=True,
               last_multiplier_notified=_stamp_date(cycle_start, True),
               _actually_delivered=True),
        MCN, expected_missed=False, expected_gap=None, note="clean send")


def _threshold_record(rng: random.Random, i: int) -> LabeledRecord:
    rid = f"T{i:05d}"
    tiers = [80, 90, 100]
    roll = rng.random()
    if roll < SILENT_FAIL_RATE:
        # crossed 80, delivered, but tier never stamped -> silent failure
        return LabeledRecord(
            Record(rid, subscribed_thresholds=tiers, usage_percentage=85,
                   thresholds_notified=[], _actually_delivered=True),
            THRESHOLD, expected_missed=True, expected_gap="threshold_silent_failure",
            note="delivered but tier not stamped (silent failure)")
    if roll < SILENT_FAIL_RATE + BASE_MISSED_RATE:
        return LabeledRecord(
            Record(rid, subscribed_thresholds=tiers, usage_percentage=100,
                   thresholds_notified=[], _actually_delivered=None),
            THRESHOLD, expected_missed=True, expected_gap=None, note="crossed tier, not stamped (missed)")
    # already stamped for the highest crossed tier -> not missed
    return LabeledRecord(
        Record(rid, subscribed_thresholds=tiers, usage_percentage=92,
               thresholds_notified=[80, 90], _actually_delivered=True),
        THRESHOLD, expected_missed=False, expected_gap=None, note="highest crossed tier already sent")


def generate(n_per_process: int = 200, seed: int = 20260902) -> list[LabeledRecord]:
    """Generate a labeled synthetic corpus of ~3*n_per_process records."""
    rng = random.Random(seed)
    corpus: list[LabeledRecord] = []
    cycle_start = "2026-09-01"
    for i in range(n_per_process):
        corpus.append(_mas_record(rng, i, cycle_start))
        corpus.append(_mcn_record(rng, i, cycle_start))
        corpus.append(_threshold_record(rng, i))
    return corpus


if __name__ == "__main__":
    corpus = generate()
    by_note: dict[str, int] = {}
    for lr in corpus:
        by_note[lr.note] = by_note.get(lr.note, 0) + 1
    print(f"generated {len(corpus)} labeled synthetic records")
    for note, count in sorted(by_note.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {note}")
