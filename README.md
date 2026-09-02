# Customer Notification Assurance Agent

An autonomous reconciliation-and-diagnosis assistant for entitlement operations.
Built for the Agentic AI capstone. **All data is synthetic / anonymized — no
proprietary, confidential, or real customer information is included.**

## The problem

Operations teams send customers several required communications on different
cadences — monthly account statements, quarterly multiplier-change notices, and
daily usage-threshold alerts. Someone has to confirm that everyone who was
*eligible* actually got their notice, and chase the ones who didn't. That check
is done manually today: export eligibility, compare against what the system
marked "sent," eyeball the gaps. It is slow, doesn't scale across three cadences,
and misses a critical blind spot: **there is no separate delivery log — the
"sent" stamp on the record is the only proof-of-send.** So a notice that was
stamped but silently bounced *looks* delivered and never gets investigated.

**Intended users:** an entitlement operations analyst (daily) and their team lead
(oversight).

## What the agent does

Per notification cycle it runs an end-to-end assurance pass:

1. **Reconcile** — exact set logic compares *eligible-this-cycle* vs.
   *stamped-this-cycle* and returns the missed set (deterministic, no retrieval).
2. **Detect observability gaps** — a simulated external delivery probe surfaces
   failures the source system can't see: `stamped_but_bounced` and
   `threshold_silent_failure` (a lost proof-of-send stamp).
3. **Classify** — a semantic retrieval layer (RAG) grounds *why* each gap
   happened against anonymized runbooks + a reason-code glossary, and degrades to
   human review when confidence is low.
4. **Route** — produces a prioritized, evidence-backed exception list; low-
   confidence and high-impact findings escalate to a human.

A ReAct-style loop ties these together and logs a full trajectory.

## Architecture

```
Reconcile (eligible vs stamped) → Detect observability gaps → Classify (RAG) → Route
      deterministic core              external delivery probe      grounded         escalate/report
                        └────────── ReAct loop, trajectory logged ──────────┘
```

The core design idea is a **hybrid split**: exact work (counting) is
deterministic because counts must never hallucinate; judgment work (*why* a
record was missed) is grounded by retrieval. Guardrails, read-only tools, and
human-in-the-loop wrap the loop.

## Repository layout

```
notification-assurance-agent/
├── src/                      # core agent logic (importable modules)
│   ├── agent.py              #   ReAct-style orchestration tying the halves together
│   ├── model.py              #   synthetic records + proof-of-send stamp fields
│   ├── reconciliation.py     #   deterministic per-process eligible-vs-stamped logic (no RAG)
│   ├── gaps.py               #   observability-gap detection via a simulated delivery probe
│   └── retrieval.py          #   dependency-free semantic retrieval (top-k, threshold, metadata filter)
├── knowledge_base/           # anonymized runbooks + reason-code glossary the RAG layer indexes
├── scripts/
│   └── run_demo.py           # runs all three processes + the "why grounding matters" contrast
├── tests/
│   └── test_reconciliation.py# deterministic tests for the core + grounded agent
├── docs/
│   ├── ARCHITECTURE.md        # design → code mapping
│   └── CODE_NOTES.md          # module-level notes
├── SAMPLE_OUTPUT.txt          # captured demo output (sample evaluation artifact)
└── README.md
```

## Run it

```bash
python3 scripts/run_demo.py
```

Run the tests:

```bash
python3 tests/test_reconciliation.py     # no dependencies
# or, if you have pytest:  pytest tests/
```

No third-party dependencies — pure Python standard library, so it runs anywhere
with Python 3.10+.

## Evaluation

The demo includes a **contrast test**: the grounded agent vs. a naive
raw-field reconciliation on the same synthetic records. The agent removes false
positives (suppressed accounts, throttled sends) and surfaces high-severity
failures the stamp-only source system cannot see (bounces, silent stamp-update
losses). See `SAMPLE_OUTPUT.txt` for a full run.

**Known limitation:** on the small synthetic corpus, retrieval similarity scores
are low, so most classifications conservatively route to human review. A larger,
tuned knowledge base and recalibrated thresholds are the next step.

## Data & privacy

Every field name and record in this repository is synthetic or anonymized. The
model reproduces the *shape* of a real notification architecture (three
processes, a proof-of-send stamp, no delivery log) without any proprietary
identifiers.
