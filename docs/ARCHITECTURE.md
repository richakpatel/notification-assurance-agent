# Architecture

This document maps the design concepts to the code, so a reviewer can trace each
idea to where it lives. All data is synthetic / anonymized.

## The hybrid split (the core idea)

Exact work is deterministic; judgment work is grounded by retrieval.

```
Reconciler ───▶ Classifier ───▶ Investigator ───▶ Reporter
(eligible vs     (detect gaps +    (Tree-of-Thought   (synthesize
 stamped,         RAG grounding,     root-cause on      the report)
 deterministic)   human-review       the ambiguous
                  fallback)          tail)
                       ▲__________________│
                     advisory feedback edge
       └────────── shared state, one trajectory logged ──────────┘
```

The four agents (Checkpoint 5.1) run as a directed pipeline over one shared
`CycleState`. Inside it, the deterministic reconciliation core and the RAG
classifier are unchanged from 3.1; the Investigator adds a Tree-of-Thought
root-cause search (4.1) on the ambiguous tail. All core modules live in the
`notification_agent` package under `src/`.

| Concept | Where it lives | Notes |
|---|---|---|
| Deterministic reconciliation | `src/notification_agent/reconciliation.py` | Exact set logic: eligible-this-cycle vs stamped-this-cycle. **No RAG** — counts must never hallucinate. |
| Per-process eligibility rules | `src/notification_agent/reconciliation.py` (`_eligible_mas`, `_eligible_mcn`, threshold tier logic) | Anonymized restatements of the real eligibility predicates. |
| Observability-gap detection | `src/notification_agent/gaps.py` | Simulated external delivery probe surfaces `stamped_but_bounced` and `threshold_silent_failure` — failures the source system cannot see because the stamp is the only proof-of-send. |
| RAG classification | `src/notification_agent/retrieval.py` + `src/notification_agent/agent.py` (`_classify`) | TF cosine retrieval over `data/knowledge_base/`, top-k with a similarity threshold and metadata pre-filter by notification type. |
| Confidence → human review | `src/notification_agent/agent.py` (`SIMILARITY_THRESHOLD` fallback) | Below threshold, the finding degrades to `needs_review` instead of forcing a match. |
| Tree-of-Thought root cause | `src/notification_agent/tot.py` (`investigate`) | BFS beam search (b≈4, T=3) over `[symptom, evidence, candidate-cause]`; value = confirmed/plausible/refuted (sampled ×3); confirmed gated on deterministic corroboration; near-ties → human review. Runs only on the ambiguous tail (Checkpoint 4.1). |
| Four-agent pipeline | `src/notification_agent/pipeline.py` (`AssurancePipeline`, `CycleState`) | Reconciler → Classifier → Investigator → Reporter over shared state, with one advisory feedback edge (Investigator → Classifier). LangGraph-style directed topology (Checkpoint 5.1). |
| Orchestration entry point | `src/notification_agent/agent.py` (`run_cycle`) | Builds and runs the pipeline; keeps `_classify` (the ReAct-style Reason→Act→Observe classification from 2.1) that the Classifier agent calls. Emits one unified trajectory. |
| Synthetic sample data | `src/notification_agent/sample_data.py` (`build_records`) | The teaching-case records shared by the demo, the tests, and the API's `/demo` route. |
| Labeled validation corpus | `src/notification_agent/synthetic_data.py` (`generate` → `generate_synthetic_corpus`) | Seeded, labeled 600-record corpus (200/process); each record paired with the ground-truth outcome. Population shape from anonymized aggregate ratios only. |
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

## Tree-of-Thought root-cause search (`tot.py`)

Reconciliation names *which* records were missed. The Investigator answers *why*,
running a faithful ToT-BFS search (Yao et al. 2023, Algorithm 1) per ambiguous
finding:

- **State / node** = `[symptom, evidence-so-far, candidate cause]`.
- **Depth 1 (propose)** — branch the symptom into candidate cause *categories*
  (`expected_non_send`, `delivery_failure`, `genuine_miss`, `data_integrity`);
  score each by look-ahead and keep the top-`b` (beam width ≈ 4).
- **Depth 2 (corroborate)** — expand surviving categories into specific reason
  codes (the glossary vocabulary), evaluate each, and **prune refuted branches**.
- **Depth 3 (decide)** — a cause is `confirmed` only with deterministic
  corroboration and a clear margin; a near-tie or a merely-`plausible` best cause
  routes to **human review**.
- **Value** = `confirmed / plausible / refuted`, weighted 20 / 1 / 0.001 and
  sampled ×3 (the paper's sampled evaluator).

**Honest note on the "reasoning":** this repo is zero-dependency and calls **no
LLM**. The thought *generator* and *evaluator* are deterministic heuristics over
the record's evidence signals — honest stand-ins for what would be model calls in
production. What is implemented in full is the ToT *control structure* (branching,
per-level value evaluation, beam pruning, depth bound, decision rule); an LLM
generator/evaluator would slot in without changing the search. This mirrors the
deterministic mock backend the reference capstones ship alongside their model
backend.

## Four-agent coordination (`pipeline.py`)

The pipeline runs `Reconciler → Classifier → Investigator → Reporter` over one
shared `CycleState` (a blackboard). Communication is mostly one-way along the
edges; the single two-way edge is **Investigator → Classifier**: when the ToT
search confirms a cause that would reframe a finding (e.g. an ambiguous miss is
really an expected non-send), the Investigator posts an *advisory* message. In the
safe default configuration that message is logged and surfaced, but the
**deterministic reconciliation counts stay authoritative** — the agent never
silently downgrades a miss on its own reasoning; a human confirms. This keeps the
"counts must never hallucinate" rule (3.1) and the human-in-the-loop backstop
(6.1) intact, and is why adding the Investigator does not change the validation
metrics below.

## Evaluation

`scripts/run_demo.py` runs all three processes and prints a **contrast test**: the
grounded agent vs. a naive raw-field reconciliation on the same synthetic records.
See `SAMPLE_OUTPUT.txt` for a captured run. `tests/test_reconciliation.py` asserts
the deterministic counts, suppression handling, throttle logic, high-severity
bounce escalation, and low-confidence routing.

For a quantitative measure, `scripts/validate_agent.py` runs the agent over the
labeled synthetic corpus (`synthetic_data.py`, 600 records) and scores it against
ground truth with confusion matrices on two dimensions — *missed detection*
(eligible-vs-stamped) and *gap detection* (bounces, silent stamp losses). It
prints per-process and overall precision/recall and exits non-zero on any
mismatch, so it doubles as a regression test (also wrapped in
`tests/test_validation_corpus.py`). Current result: precision = recall = 1.000 on
both dimensions across all 600 records, with zero false positives. Because the
reconciliation core is deterministic and the gap probe is exact, this measures
that the eligibility predicates, throttle/suppression guards, highest-tier logic,
and gap classification are wired correctly end-to-end — not statistical accuracy
of a model.

## Known limitation

On the small synthetic corpus, retrieval similarity scores are low (~0.2–0.4), so
most classifications conservatively route to human review. That is the safe
direction to fail; a larger, tuned knowledge base with recalibrated thresholds is
the next step.
