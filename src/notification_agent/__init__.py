"""
Customer Notification Assurance Agent (synthetic / anonymized demo).

A hybrid reconciliation-and-diagnosis agent for entitlement operations:
  * deterministic reconciliation core   (reconciliation.py)
  * observability-gap detector          (gaps.py)
  * RAG-grounded classifier             (retrieval.py + agent.py)
  * ReAct-style orchestration           (agent.py)

All data in this package is SYNTHETIC / ANONYMIZED. No proprietary field names
or real records appear anywhere.

Public API:
    from notification_agent import NotificationAssuranceAgent, build_records
    from notification_agent import MAS, MCN, THRESHOLD, Record
"""

from __future__ import annotations

from .model import MAS, MCN, STAMP_FIELD, THRESHOLD, Record
from .reconciliation import ReconciliationResult, reconcile
from .gaps import ObservabilityGap, detect_gaps
from .retrieval import KnowledgeBase, SIMILARITY_THRESHOLD, build_default_kb
from .agent import CycleReport, Finding, NotificationAssuranceAgent
from .sample_data import build_records
from .synthetic_data import LabeledRecord, generate as generate_synthetic_corpus

__version__ = "1.0.0"

__all__ = [
    # constants / model
    "MAS",
    "MCN",
    "THRESHOLD",
    "STAMP_FIELD",
    "Record",
    # reconciliation
    "ReconciliationResult",
    "reconcile",
    # gaps
    "ObservabilityGap",
    "detect_gaps",
    # retrieval
    "KnowledgeBase",
    "SIMILARITY_THRESHOLD",
    "build_default_kb",
    # agent
    "NotificationAssuranceAgent",
    "CycleReport",
    "Finding",
    # sample data
    "build_records",
    # synthetic validation corpus
    "LabeledRecord",
    "generate_synthetic_corpus",
    "__version__",
]
