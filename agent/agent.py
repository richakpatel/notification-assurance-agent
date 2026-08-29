"""
Customer Notification Assurance Agent -- hybrid orchestration.

Ties together the two halves of the design:
  1. Deterministic reconciliation (reconciliation.py) -- eligible-this-cycle vs.
     stamped-this-cycle, exact set logic, no RAG.
  2. RAG-grounded classification (retrieval.py) -- grounds WHY a record is a gap and
     what to do, over anonymized runbooks/glossary.
  3. Observability-gap detection (gaps.py) -- surfaces failures the source system
     cannot see (stamped-but-bounced, threshold silent failure), using an external
     delivery probe as the grounding source the org lacks internally.

Flow mirrors the ReAct loop from Checkpoint 2.1:
  Reason -> Act (reconcile) -> Observe -> Act (detect gaps) -> Observe ->
  Reason (classify each finding from grounded context) -> Act (route).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gaps import ObservabilityGap, detect_gaps
from model import Record
from reconciliation import ReconciliationResult, reconcile
from retrieval import KnowledgeBase, SIMILARITY_THRESHOLD, build_default_kb


@dataclass
class Finding:
    record_id: str
    notification_type: str
    observed: str            # what the reconciliation/gap step observed
    reason_code: str
    category: str            # expected_non_send | real_failure | transient | needs_review
    counts_as_missed: bool
    escalate: bool
    severity: str            # high | medium | low
    confidence: float
    grounded_by: str | None


@dataclass
class CycleReport:
    result: ReconciliationResult
    findings: list[Finding]
    missed_count: int
    escalations: list[Finding]
    trace: list[str]


_CATEGORY_RULES = {
    "expected_non_send": dict(counts_as_missed=False, escalate=False, severity="low"),
    "transient":         dict(counts_as_missed=False, escalate=False, severity="low"),
    "real_failure":      dict(counts_as_missed=True,  escalate=True,  severity="medium"),
    "needs_review":      dict(counts_as_missed=True,  escalate=True,  severity="high"),
}


def _category_for(chunk_text: str, fallback_reason: str) -> str:
    m = re.search(r"category:\s*([a-z_]+)", chunk_text)
    if m:
        return m.group(1)
    return "needs_review"


class NotificationAssuranceAgent:
    def __init__(self, kb: KnowledgeBase | None = None) -> None:
        self.kb = kb or build_default_kb()

    def _classify(self, notification_type: str, record_id: str, observed: str,
                  query_hint: str, trace: list[str]) -> Finding:
        """RAG-grounded classification of one finding (an Act+Observe step)."""
        query = f"{notification_type} {query_hint}"
        results = self.kb.query(query, notification_type=notification_type)
        top = results[0] if results else None
        trace.append(
            f"    retrieve('{query_hint}', {notification_type}) -> "
            + (f"{top.chunk.source}#{top.chunk.reason_code} score={top.score:.3f}"
               if top else "no results"))

        if top is None or top.score < SIMILARITY_THRESHOLD:
            trace.append("      below threshold -> human review (unknown)")
            rules = _CATEGORY_RULES["needs_review"]
            return Finding(record_id, notification_type, observed, "unknown",
                           "needs_review", rules["counts_as_missed"],
                           rules["escalate"], rules["severity"],
                           (top.score if top else 0.0), None)

        reason = top.chunk.reason_code or "unknown"
        category = _category_for(top.chunk.text, reason)
        rules = _CATEGORY_RULES.get(category, _CATEGORY_RULES["needs_review"])
        trace.append(f"      grounded -> reason={reason} category={category} "
                     f"missed={rules['counts_as_missed']} escalate={rules['escalate']}")
        return Finding(record_id, notification_type, observed, reason, category,
                       rules["counts_as_missed"], rules["escalate"],
                       rules["severity"], top.score, top.chunk.source)

    def run_cycle(self, notification_type: str, period: str, cycle_start: str,
                  records: list[Record]) -> CycleReport:
        trace: list[str] = []
        trace.append(f"REASON: run {notification_type} assurance for {period}")

        # Act: deterministic reconciliation (eligible vs. stamped).
        result = reconcile(notification_type, period, cycle_start, records)
        trace.append(
            f"ACT reconcile -> eligible={result.eligible_count} "
            f"stamped={result.delivered_count} missed={result.missed_count}")

        # Act: observability-gap detection via external delivery probe.
        obs_gaps = detect_gaps(result, records, cycle_start)
        trace.append(f"ACT detect_gaps -> {len(obs_gaps)} observability gap(s)")

        findings: list[Finding] = []

        # Classify each missed (eligible-not-stamped) record, grounded by RAG.
        gap_kinds = {g.record_id: g for g in obs_gaps}
        for rid in result.missed_ids:
            # If an observability gap explains this miss, use its kind as the hint.
            if rid in gap_kinds:
                g = gap_kinds[rid]
                findings.append(self._classify(
                    notification_type, rid, g.kind, g.kind, trace))
            else:
                findings.append(self._classify(
                    notification_type, rid, "eligible_not_stamped",
                    "eligible not stamped missed", trace))

        # Classify high-severity stamped-but-bounced gaps (not in missed set).
        for g in obs_gaps:
            if g.kind == "stamped_but_bounced":
                findings.append(self._classify(
                    notification_type, g.record_id, g.kind, g.kind, trace))

        # Suppressed / expected non-sends among eligible records aren't missed;
        # the reconciliation already excludes them from eligible, so nothing to do.

        missed = sum(1 for f in findings if f.counts_as_missed)
        escalations = [f for f in findings if f.escalate]
        trace.append(f"REASON: missed={missed} escalations={len(escalations)}")
        return CycleReport(result, findings, missed, escalations, trace)
