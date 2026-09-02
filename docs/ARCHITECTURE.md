# Architecture

This document maps the design concepts to the code, so a reviewer can trace each
idea to where it lives. All data is synthetic / anonymized.

## The hybrid split (the core idea)

Exact work is deterministic; judgment work is grounded by retrieval.

```
Reconcile (eligible vs stamped) → Detect observability gaps → Classify (RAG) → Route
      deterministic core              external delivery probe      grounded         escalate/report
                        └────────── ReAct loop, trajectory logged ──────────┘
```

All core modules live in the `notification_agent` package under `src/`.

| Concept | Where it lives | Notes |
|---|---|---|
| Deterministic reconciliation | `src/notification_agent/reconciliation.py` | Exact set logic: eligible-this-cycle vs stamped-this-cycle. **No RAG** — counts must never hallucinate. |
| Per-process eligibility rules | `src/notification_agent/reconciliation.py` (`_eligible_mas`, `_eligible_mcn`, threshold tier logic) | Anonymized restatements of the real eligibility predicates. |
| Observability-gap detection | `src/notification_agent/gaps.py` | Simulated external delivery probe surfaces `stamped_but_bounced` and `threshold_silent_failure` — failures the source system cannot see because the stamp is the only proof-of-send. |
| RAG classification | `src/notification_agent/retrieval.py` + `src/notification_agent/agent.py` (`_classify`) | TF cosine retrieval over `data/knowledge_base/`, top-k with a similarity threshold and metadata pre-filter by notification type. |
| Confidence → human review | `src/notification_agent/agent.py` (`SIMILARITY_THRESHOLD` fallback) | Below threshold, the finding degrades to `needs_review` instead of forcing a match. |
| ReAct orchestration | `src/notification_agent/agent.py` (`run_cycle`) | Reason → Act (reconcile) → Observe → Act (detect gaps) → Reason (classify) → Route, with a full trajectory trace. |
| Synthetic sample data | `src/notification_agent/sample_data.py` (`build_records`) | The teaching-case records shared by the demo, the tests, and the API's `/demo` route. |
| Console demo | `src/notification_agent/__main__.py` | Runs all three processes + the contrast test; invoked by `scripts/run_demo.py`, `python3 -m notification_agent`, or the `notification-agent-demo` command. |
| HTTP JSON API | `api/server.py` | Zero-dependency `http.server` wrapper exposing the agent: `GET /health`, `GET /demo`, `POST /reconcile`. Read-only, like the agent itself. |

## The three processes

| Process | Cadence | Stamp field (synthetic) | Eligibility gist |
|---|---|---|---|
| MAS (monthly statement) | monthly | `last_statement_notified` | active/recently-ended, subscribed, started ≤ last month, not suppressed |
| MCN (multiplier notice) | quarterly | `last_multiplier_notified` | active, subscribed, multiplier effective soon, outside the ~80-day throttle |
| THRESHOLD (usage alert) | daily | `thresholds_notified` (list of tiers) | subscribed to a crossed tier not already stamped |

(Stamp field names above are synthetic. They are defined in
`src/notification_agent/model.py`.)

## Data model

`src/notification_agent/model.py` defines a single flat synthetic `Record` carrying every signal the
three processes read and stamp. In a real system these would live on separate
related objects; one flat record keeps the demo readable. A hidden
`_actually_delivered` flag exists **only** so the demo can show the
stamped-but-bounced gap — the agent reads it solely through the simulated probe in
`gaps.py`, never directly.

## Evaluation

`scripts/run_demo.py` runs all three processes and prints a **contrast test**: the
grounded agent vs. a naive raw-field reconciliation on the same synthetic records.
See `SAMPLE_OUTPUT.txt` for a captured run. `tests/test_reconciliation.py` asserts
the deterministic counts, suppression handling, throttle logic, high-severity
bounce escalation, and low-confidence routing.

## Known limitation

On the small synthetic corpus, retrieval similarity scores are low (~0.2–0.4), so
most classifications conservatively route to human review. That is the safe
direction to fail; a larger, tuned knowledge base with recalibrated thresholds is
the next step.
