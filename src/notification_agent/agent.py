"""
Customer Notification Assurance Agent -- hybrid orchestration.

Ties together the halves of the design as a four-agent pipeline (Checkpoint 5.1):
  1. Reconciler   (reconciliation.py) -- eligible-this-cycle vs. stamped-this-cycle,
     exact set logic, no RAG.
  2. Classifier   (retrieval.py + gaps.py) -- detects observability gaps and RAG-
     grounds WHY each record is a gap, over anonymized runbooks/glossary.
  3. Investigator (tot.py) -- Tree-of-Thought root-cause search on the ambiguous
     tail (Checkpoint 4.1).
  4. Reporter     (pipeline.py) -- synthesizes the final CycleReport.

`NotificationAssuranceAgent.run_cycle` builds and runs that pipeline. It still
exposes `_classify` (the RAG-grounded classification of one finding), which the
Classifier agent calls -- keeping the ReAct-style reasoning and trajectory log
from Checkpoint 2.1 intact while the pipeline structure matches 4.1 / 5.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import Record
from .reconciliation import ReconciliationResult
from .retrieval import KnowledgeBase, SIMILARITY_THRESHOLD, build_default_kb
from .tot import RootCause


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
    root_cause: RootCause | None = None   # set by the Investigator on the ambiguous tail


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
        """Run the four-agent assurance pipeline for one cycle.

        Reconciler -> Classifier -> Investigator (ToT) -> Reporter, over shared
        state. The deterministic reconciliation counts remain authoritative; the
        Investigator only *adds* a root cause to the ambiguous tail."""
        from .pipeline import AssurancePipeline   # local import avoids a cycle
        return AssurancePipeline(self._classify).run(
            notification_type, period, cycle_start, records)
