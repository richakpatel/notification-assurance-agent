"""
Four-agent coordination pipeline (Checkpoint 5.1) -- zero dependency.

A LangGraph-style directed pipeline over a shared CycleState. Four agents, each a
node with a single responsibility (inside the 3-5 agent sweet spot, Guo et al. 2024):

    Reconciler  ->  Classifier  ->  Investigator  ->  Reporter
   (eligible vs     (RAG grounds     (ToT root-cause    (synthesize the
    stamped,         each gap,        on the ambiguous    final report)
    deterministic)   degrades to      tail -- 4.1)
                     human review)
                          ^________________|
                       advisory feedback edge
                     (Investigator -> Classifier)

Communication is mostly one-way along the pipeline edges. The one two-way edge is
Investigator -> Classifier: when the ToT search confirms a cause that would
reframe a finding (e.g. an ambiguous miss is really an expected non-send), the
Investigator posts an advisory message back. In this SAFE default configuration
that message is logged and surfaced, but the DETERMINISTIC reconciliation counts
stay authoritative -- the agent never silently downgrades a miss on its own
reasoning; a human confirms. This mirrors the "counts must never hallucinate"
rule (3.1) and the human-in-the-loop backstop (6.1).

Every agent writes to the shared CycleState and appends to one trajectory log,
so the whole multi-agent run is observable end to end.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gaps import ObservabilityGap, detect_gaps
from .model import Record
from .reconciliation import ReconciliationResult, reconcile
from .tot import RootCause, investigate


@dataclass
class CycleState:
    """Shared state the four agents read and write (the pipeline's blackboard)."""
    notification_type: str
    period: str
    cycle_start: str
    records: list[Record]
    result: ReconciliationResult | None = None
    obs_gaps: list[ObservabilityGap] = field(default_factory=list)
    findings: list = field(default_factory=list)              # list[Finding]
    root_causes: dict = field(default_factory=dict)           # record_id -> RootCause
    messages: list[str] = field(default_factory=list)         # agent-to-agent notes
    trace: list[str] = field(default_factory=list)            # unified trajectory


class ReconcilerAgent:
    """Deterministic eligible-vs-stamped reconciliation (no RAG)."""
    name = "Reconciler"

    def run(self, state: CycleState) -> None:
        state.result = reconcile(state.notification_type, state.period,
                                 state.cycle_start, state.records)
        r = state.result
        state.trace.append(
            f"[Reconciler] eligible={r.eligible_count} stamped={r.delivered_count} "
            f"missed={r.missed_count}")


class ClassifierAgent:
    """Detects observability gaps, then RAG-grounds each finding. Degrades to
    human review below the retrieval similarity threshold. `classify_fn` is the
    agent's `_classify` method, injected to avoid an import cycle."""
    name = "Classifier"

    def __init__(self, classify_fn) -> None:
        self._classify = classify_fn

    def run(self, state: CycleState) -> None:
        result = state.result
        nt = state.notification_type
        state.obs_gaps = detect_gaps(result, state.records, state.cycle_start)
        state.trace.append(f"[Classifier] detect_gaps -> {len(state.obs_gaps)} "
                           "observability gap(s)")

        gap_kinds = {g.record_id: g for g in state.obs_gaps}
        findings = []
        for rid in result.missed_ids:
            if rid in gap_kinds:
                g = gap_kinds[rid]
                findings.append(self._classify(nt, rid, g.kind, g.kind, state.trace))
            else:
                findings.append(self._classify(
                    nt, rid, "eligible_not_stamped",
                    "eligible not stamped missed", state.trace))
        # High-severity stamped-but-bounced gaps live outside the missed set.
        for g in state.obs_gaps:
            if g.kind == "stamped_but_bounced":
                findings.append(self._classify(nt, g.record_id, g.kind, g.kind, state.trace))
        state.findings = findings


class InvestigatorAgent:
    """Runs the ToT root-cause search on the AMBIGUOUS TAIL only -- findings that
    routed to human review. Attaches a RootCause to each and, when the confirmed
    cause reframes the finding, posts an advisory message back to the Classifier
    (the one two-way edge). Advisory only: deterministic counts are unchanged."""
    name = "Root-Cause Investigator"

    def run(self, state: CycleState) -> None:
        by_id = {r.record_id: r for r in state.records}
        tail = [f for f in state.findings if f.category == "needs_review"]
        state.trace.append(f"[Investigator] ambiguous tail -> {len(tail)} finding(s) "
                           "for ToT root-cause")
        for f in tail:
            record = by_id.get(f.record_id)
            if record is None:
                continue
            probe = record._actually_delivered
            rc: RootCause = investigate(f.observed, record, f.notification_type,
                                        probe, state.cycle_start)
            f.root_cause = rc
            state.root_causes[f.record_id] = rc
            for line in rc.trajectory:
                state.trace.append("    " + line)

            # Two-way edge: a confirmed expected-non-send reframes the finding.
            if rc.verdict == "confirmed" and rc.cause in (
                    "suppressed", "throttle_window", "threshold_reset"):
                msg = (f"[Investigator->Classifier] {f.record_id}: confirmed root "
                       f"cause '{rc.cause}' suggests expected_non_send; deterministic "
                       "count left unchanged, flagged for human confirmation")
                state.messages.append(msg)
                state.trace.append("    " + msg)


class ReporterAgent:
    """Synthesizes the final CycleReport from shared state."""
    name = "Reporter"

    def run(self, state: CycleState):
        from .agent import CycleReport      # local import avoids a cycle
        missed = sum(1 for f in state.findings if f.counts_as_missed)
        escalations = [f for f in state.findings if f.escalate]
        confirmed = sum(1 for rc in state.root_causes.values()
                        if rc.verdict == "confirmed")
        state.trace.append(
            f"[Reporter] missed={missed} escalations={len(escalations)} "
            f"root-causes-confirmed={confirmed}/{len(state.root_causes)}")
        return CycleReport(state.result, state.findings, missed, escalations, state.trace)


class AssurancePipeline:
    """Runs the four agents in order over one shared CycleState."""

    def __init__(self, classify_fn) -> None:
        self.agents = [
            ReconcilerAgent(),
            ClassifierAgent(classify_fn),
            InvestigatorAgent(),
            ReporterAgent(),
        ]

    def run(self, notification_type: str, period: str, cycle_start: str,
            records: list[Record]):
        state = CycleState(notification_type, period, cycle_start, records)
        state.trace.append(
            f"PLAN: {' -> '.join(a.name for a in self.agents)}  (shared-state pipeline)")
        state.trace.append(f"REASON: run {notification_type} assurance for {period}")
        report = None
        for agent in self.agents:
            report = agent.run(state)      # only the Reporter returns a value
        return report
