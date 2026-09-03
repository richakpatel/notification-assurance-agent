# Threshold Usage-Alert Gap Investigation (worked example)

> **SYNTHETIC / ANONYMIZED.** Every number, identifier, product name, and config
> value below is fabricated for the demo. This document reproduces the *shape* of
> a real daily usage-threshold notification gap investigation — it contains no
> real customer, contract, or company data.

Threshold notifications (usage alerts) run **daily** and fire per tier: an
entitlement crossing 80%, 90%, or 100% of its usage allowance should get an alert
for each band it crosses. Because the process is daily and tier-based, gaps must
be read **for a single day** and **per tier** — an all-time comparison is
meaningless here.

## Apparent gap

For the **2026-10-05** run, a same-day query returns **340** usage records that
crossed a threshold band but carry no notification stamp for that band. Scoping to
one day matters: the raw "ever stamped" count is far larger and would drown out
today's real signal.

### Tier breakdown (2026-10-05)

| Crossed band | Records | Stamped for that band | Outstanding |
|---|---:|---:|---:|
| 80%  | 210 | 150 | 60 |
| 90%  | 95  | 70  | 25 |
| 100% | 35  | 20  | 15 |

## The causes the agent separates

### 1. Already satisfied (expected non-send)

A record at 92% usage that is already stamped for both **80** and **90** has no
outstanding band (100 is not yet due). It looks eligible to a naive "subscribed to
thresholds?" check but is fully satisfied. The agent excludes it — no miss.

### 2. Silent stamp-update failure (the invisible one)

The dangerous case: usage crossed **80%**, the alert was **delivered**, but the
crossed tier was never written to the stamp list. The stamp-update failure is only
**debug-logged**, so a stamp-only monitor cannot see it — the record simply looks
un-notified.

```
delivered = true  AND  crossed tier NOT in thresholds_notified
   -> threshold_silent_failure  (high severity)
```

Only a delivery probe cross-checked against the stamp exposes this. The agent
confirms it as a `threshold_silent_failure` and escalates it — a proof-of-send
loss that would otherwise vanish.

### 3. Genuine miss

Usage crossed a band, nothing was delivered, nothing was stamped. A true send
failure — escalated.

## Highest-tier logic

When a record crosses multiple bands at once (e.g. jumps straight to 100%), the
agent reconciles against the **highest** crossed tier rather than double-counting
each band. This keeps the missed count honest when usage spikes across several
thresholds in a single day.

## What the agent concludes

- Same-day, per-tier scoping — not an all-time stamp count.
- Already-satisfied tiers **excluded**; genuine misses and, crucially,
  **silent stamp-update failures** surfaced and escalated.

The lesson threshold teaches the design: some failures are **invisible to the
source system by construction** — when the only proof-of-send is a stamp and the
stamp-write can fail silently, you need an independent delivery signal to catch a
delivered-but-unstamped alert.
