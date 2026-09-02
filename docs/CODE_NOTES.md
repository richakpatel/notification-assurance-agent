# Customer Notification Assurance Agent — working demo

Hybrid agent for the capstone. **All data is synthetic / QA only.** It models three
real notification processes (anonymized) and does two jobs:

1. **Missed-send detector** — deterministic reconciliation of *eligible-this-cycle*
   vs. *stamped-this-cycle* for each process (MAS monthly, MCN multiplier, Threshold).
2. **Observability-gap closer** — surfaces failures the source system cannot see:
   `stamped_but_bounced` and the threshold `threshold_silent_failure`, using an
   external delivery probe as grounding the org does not keep internally.

The **why**/classification is grounded by a semantic retrieval layer (RAG) over
anonymized runbooks + a reason-code glossary in `data/knowledge_base/`.

## Key real-world fact captured
There is **no separate delivery-log object** in the source system — the stamp field
IS the only proof-of-send. So a record eligible-but-not-stamped after the run window
is a missed notification, and a stamped-but-bounced email is invisible internally.

## Files (in the `notification_agent` package under `src/`)
- `model.py` — synthetic records + stamp fields (anonymized; mapping in comments).
- `reconciliation.py` — deterministic eligible-vs-stamped logic per process (no RAG).
- `gaps.py` — observability-gap detection via a simulated external delivery probe.
- `retrieval.py` — dependency-free semantic retrieval (top-k, threshold, metadata filter).
- `agent.py` — ReAct-style orchestration tying the halves together.
- `sample_data.py` — synthetic sample records shared by the demo, tests, and API.
- `__main__.py` — runs all three processes and the "why grounding matters" contrast.

Outside the package:
- `data/knowledge_base/` — anonymized runbooks + reason-code glossary the RAG layer indexes.
- `api/server.py` — zero-dependency HTTP JSON API (`/health`, `/demo`, `/reconcile`).
- `scripts/run_demo.py` — zero-install entry point for the console demo.

## Run
```
python3 scripts/run_demo.py          # zero install
python3 -m notification_agent        # after `pip install -e .`
python3 api/server.py                # JSON API on http://127.0.0.1:8000
```
No third-party dependencies (pure standard library).
