"""
Tree-of-Thought root-cause investigation (Checkpoint 4.1) -- zero dependency.

Reconciliation names the *missed set* deterministically (e.g. 1000 eligible /
800 stamped -> 200 missed). This module reasons about WHY each *ambiguous* miss
happened, using the ToT-BFS control structure from Yao et al. 2023 (Algorithm 1)
applied to notification root-cause analysis:

  node          = [symptom, evidence-so-far, candidate cause]
  branch        = a candidate cause
  breadth  b    = ~4 candidate-cause categories proposed per expansion
  depth    T    = 3   (propose categories -> corroborate leaves -> decide)
  search        = breadth-first beam search (keep the top-b nodes per level)
  value         = confirmed / plausible / refuted   (evaluator, sampled 3x)
  gate          = a cause is only 'confirmed' with deterministic corroboration
  ties          = near-tied top causes -> human review

NO LLM is called. The thought *generator* and *evaluator* are DETERMINISTIC
heuristics over the record's evidence signals and the reason-code vocabulary --
honest stand-ins for what would be model calls in a production deployment. What
IS implemented in full is the ToT *search structure*: branching, per-level value
evaluation, beam pruning, the depth bound, and the confirmed/plausible/refuted
decision rule. Swapping the generator/evaluator for LLM calls would not change
the search. (This mirrors how the reference capstones ship a deterministic mock
backend alongside the optional model backend.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import MCN, THRESHOLD, Record
from .reconciliation import (
    MCN_THROTTLE_DAYS,
    _days_between,
    _highest_crossed_tier,
)

# ---- value strategy (matches the 4.1 evaluator: sure/likely/impossible) ------

CONFIRMED = "confirmed"
PLAUSIBLE = "plausible"
REFUTED = "refuted"

# Value weights the evaluator assigns each verdict (mirrors the lab's 20/1/0.001).
_WEIGHT = {CONFIRMED: 20.0, PLAUSIBLE: 1.0, REFUTED: 0.001}

# Search parameters (see the 4.1 write-up).
BEAM_WIDTH = 4          # b -- candidates kept per level
DEPTH = 3               # T -- propose -> corroborate -> decide
SAMPLES = 3             # evaluator votes per candidate (aggregated)
_TIE_MARGIN = 0.5       # value units; within this at the top -> human review

# Candidate-cause tree: symptom -> cause CATEGORIES -> specific reason codes.
# The reason codes are the glossary vocabulary (data/knowledge_base), so a
# confirmed cause maps straight onto a runbook entry.
_CATEGORY_TREE = {
    "expected_non_send": ["suppressed", "throttle_window", "threshold_reset"],
    "delivery_failure":  ["stamped_but_bounced", "threshold_silent_failure"],
    "genuine_miss":      ["genuine_send_failure"],
    "data_integrity":    ["integrity_mismatch"],
}
_CAUSE_CATEGORY = {c: cat for cat, causes in _CATEGORY_TREE.items() for c in causes}
# Confirmed causes in these categories are actionable failures -> escalate.
_ACTIONABLE = {"delivery_failure", "genuine_miss", "data_integrity"}


@dataclass
class RootCause:
    """Result of a ToT investigation of one ambiguous finding."""
    record_id: str
    symptom: str
    cause: str                       # best candidate reason code (or "unknown")
    verdict: str                     # confirmed | plausible | refuted
    confidence: float                # normalized value score in [0, 1]
    evidence: list[str]
    escalate_to_human: bool          # True on no-confirmed-cause / near-tie
    trajectory: list[str] = field(default_factory=list)   # the ToT search trace
    ranked: list[tuple[str, float]] = field(default_factory=list)  # cause -> value


def _verdict_for(cause: str, r: Record, nt: str, probe: bool | None,
                 cycle_start: str, symptom: str) -> tuple[str, str]:
    """Deterministic corroboration of one candidate cause against the record's
    evidence. Returns (verdict, evidence-string). This is the ToT value stand-in;
    an LLM would slot in here without changing the search."""
    if cause == "suppressed":
        if nt in r.suppressed_types:
            return CONFIRMED, f"suppression flag set for {nt}"
        return REFUTED, "no suppression flag for this type"

    if cause == "throttle_window":
        if nt == MCN and r.last_multiplier_notified is not None:
            age = _days_between(cycle_start, r.last_multiplier_notified)
            if 0 <= age < MCN_THROTTLE_DAYS:
                return CONFIRMED, f"stamped {age}d ago, inside {MCN_THROTTLE_DAYS}d throttle"
        return REFUTED, "no recent stamp inside the throttle window"

    if cause == "threshold_reset":
        if nt == THRESHOLD and _highest_crossed_tier(r) is None:
            return PLAUSIBLE, "usage below all subscribed tiers (possible reset)"
        return REFUTED, "no evidence of a tier reset"

    if cause == "stamped_but_bounced":
        if probe is False:
            return CONFIRMED, "external probe shows bounce/non-delivery on a stamped record"
        if probe is None:
            return PLAUSIBLE, "delivery unverified; provider probe inconclusive"
        return REFUTED, "external probe confirms delivery"

    if cause == "threshold_silent_failure":
        if nt == THRESHOLD and probe is True:
            tier = _highest_crossed_tier(r)
            if tier is not None and tier not in r.thresholds_notified:
                return CONFIRMED, ("delivered but crossed tier missing from the stamp "
                                   "list (update failure is only debug-logged)")
        return REFUTED, "no silent stamp-update loss detected"

    if cause == "genuine_send_failure":       # -> glossary 'eligible_not_stamped'
        if symptom == "stamped_but_bounced":
            return REFUTED, "record IS stamped -- not an unstamped genuine miss"
        if probe is True:
            return REFUTED, "provider shows a delivery -- not a genuine send failure"
        if probe is False:
            return CONFIRMED, "no stamp and probe confirms non-delivery"
        return PLAUSIBLE, "no proof-of-send stamp and delivery unverified"

    if cause == "integrity_mismatch":
        return PLAUSIBLE, "independent signals disagree; data-quality review"

    return REFUTED, "no corroborating evidence"


def _aggregate(cause: str, r: Record, nt: str, probe: bool | None,
               cycle_start: str, symptom: str) -> tuple[float, str, str]:
    """Evaluate one cause SAMPLES times and aggregate (mean value weight).

    The votes are deterministic here (no stochastic model), so they are unanimous
    by construction; the aggregation mirrors the paper's sampled evaluator so an
    LLM evaluator could be dropped in without changing the caller."""
    verdict, evidence = _verdict_for(cause, r, nt, probe, cycle_start, symptom)
    votes = [_WEIGHT[verdict]] * SAMPLES
    return sum(votes) / len(votes), verdict, evidence


def investigate(symptom: str, record: Record, nt: str, probe: bool | None,
                cycle_start: str, b: int = BEAM_WIDTH, depth: int = DEPTH) -> RootCause:
    """Run a ToT-BFS root-cause search for one ambiguous finding."""
    traj: list[str] = [
        f"ToT root-cause: symptom='{symptom}' record={record.record_id} "
        f"(BFS, b={b}, T={depth})"
    ]

    # --- depth 1: PROPOSE candidate cause categories, evaluate by look-ahead ---
    depth1: list[tuple[str, float]] = []
    for cat, causes in _CATEGORY_TREE.items():
        look_ahead = max(_aggregate(c, record, nt, probe, cycle_start, symptom)[0]
                         for c in causes)
        depth1.append((cat, look_ahead))
    depth1.sort(key=lambda x: -x[1])
    beam = depth1[:b]
    traj.append("  d1 propose categories -> "
                + ", ".join(f"{c}={v:.2f}" for c, v in depth1))
    traj.append(f"  d1 beam (top {b}) -> " + ", ".join(c for c, _ in beam))

    # --- depth 2: EXPAND surviving categories into leaves, corroborate, prune ---
    leaves: list[tuple[str, float, str, str]] = []   # (cause, value, verdict, evidence)
    for cat, _ in beam:
        for cause in _CATEGORY_TREE[cat]:
            value, verdict, evidence = _aggregate(cause, record, nt, probe,
                                                   cycle_start, symptom)
            if verdict == REFUTED:
                traj.append(f"  d2 {cat}/{cause} -> refuted [pruned] ({evidence})")
                continue
            leaves.append((cause, value, verdict, evidence))
            traj.append(f"  d2 {cat}/{cause} -> {verdict} value={value:.2f} ({evidence})")
    leaves.sort(key=lambda x: -x[1])
    leaves = leaves[:b]

    # --- depth 3: DECIDE (confirmed gate + tie -> human review) ----------------
    if not leaves:
        traj.append("  d3 decide -> no surviving cause -> human review (unknown)")
        return RootCause(record.record_id, symptom, "unknown", REFUTED, 0.0,
                         ["no candidate cause survived corroboration"], True, traj, [])

    ranked = [(c, v) for c, v, _, _ in leaves]
    top_cause, top_val, top_verdict, top_ev = leaves[0]
    confidence = min(1.0, top_val / _WEIGHT[CONFIRMED])
    tie = (len(leaves) > 1
           and (leaves[0][1] - leaves[1][1]) < _TIE_MARGIN
           and leaves[1][2] != REFUTED)

    if top_verdict == CONFIRMED and not tie:
        escalate = _CAUSE_CATEGORY[top_cause] in _ACTIONABLE
        traj.append(f"  d3 decide -> CONFIRMED '{top_cause}' conf={confidence:.2f} "
                    f"(escalate={escalate}); {top_ev}")
        return RootCause(record.record_id, symptom, top_cause, CONFIRMED,
                         confidence, [top_ev], escalate, traj, ranked)

    if tie:
        traj.append(f"  d3 decide -> near-tie {leaves[0][0]} vs {leaves[1][0]} "
                    "-> human review")
    else:
        traj.append(f"  d3 decide -> best is only PLAUSIBLE '{top_cause}' "
                    "-> human review")
    return RootCause(record.record_id, symptom, top_cause, PLAUSIBLE,
                     confidence, [top_ev], True, traj, ranked)
