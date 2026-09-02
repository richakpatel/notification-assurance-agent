# MAS Statement-Period Gap Investigation (worked example)

> **SYNTHETIC / ANONYMIZED.** Every number, identifier, product name, and config
> value below is fabricated for the demo. This document reproduces the *shape* of
> a real eligibility-to-notification gap investigation — it contains no real
> customer, contract, or company data.

This is the kind of case the assurance agent is built to reason about: after a
monthly statement run, a broad monitoring query shows a population of
entitlements with no notification date for the current delivery month, and
someone has to explain *why* before escalating.

## Apparent gap

A broad monitoring query returns **3,600** entitlements with no notification date
for the August delivery window. This is a live population, not a frozen-baseline
subtraction, so part of it is expected and part is real.

### Status breakdown

| Entitlement status | Entitlements | Contracts |
|---|---:|---:|
| Active   | 2,150 | 910 |
| Inactive | 1,450 | 500 |

The 1,450 inactive entitlements are included because the monitoring query uses a
recently-ended grace window:

```
status = 'active'  OR  ended_date within the last 45 days
```

Of these, **1,300** inactive entitlements across 440 contracts still carry a
prior-cycle notification date, and 95 across 34 contracts carry the day after.
Recently-ended entitlements inside the 45-day grace window are the single largest
source of *apparent* (not real) fallout.

### Notification-date breakdown

| Last notification date | Entitlements | Contracts |
|---|---:|---:|
| Prior cycle, day 1 | 1,450 | 510 |
| Null               | 980   | 415 |
| Prior cycle, day 2 | 100   | 40  |
| Older dates        | Remaining | Remaining |

### Partner type

The gap is predominantly direct contracts:

- Direct (no reseller): 3,500 entitlements, 1,360 contracts
- All reseller types combined: 100 entitlements

### Record type

| Entitlement definition record type | Entitlements | Contracts |
|---|---:|---:|
| PlatformCore    | 3,020 | 1,200 |
| MessagingSuite  | 350   | 160   |
| IntegrationSuite| 175   | 32    |
| AnalyticsSuite  | 25    | 25    |
| CommerceSuite   | 30    | 30    |

### Usage-type concentration (largest unnotified)

- Storage Units: 820
- Service Credits: 760
- Compute Requests: 540
- Flex Units: 480
- Bulk Messages: 150
- Chat Sessions: 140
- Mobile Messages: 130

## Query-parity risk

The production notification job applies two filters the broad monitoring query
does **not** reproduce exactly:

1. `entitlement_definition.record_type IN (eligible_record_types)`
2. `contract.start_date <= LAST_MONTH`

The monitoring query used `start_date <= 2 months ago` and did not restrict to the
runtime `eligible_record_types` set. So some of the measured gap is a
**monitoring-query overcount**, not a notification-job drop.

## Runtime config retrieved

The application config store holds:

| Field | Value |
|---|---|
| Category | Statement Notification |
| Functional area | billing-ops |
| Key | eligible_record_types |
| Value | `PlatformCore;MessagingSuite` |

So the runtime job only considers `PlatformCore` and `MessagingSuite` record
types. The broad monitoring query also counted `IntegrationSuite`, `AnalyticsSuite`,
and `CommerceSuite` — **230** entitlements that are not eligible at runtime
(IntegrationSuite 175, AnalyticsSuite 25, CommerceSuite 30) and should be removed
from the gap.

## Scheduler evidence

The AMER region's first run was `ABORTED`, then rerun and completed the next day:

- Aborted job: `job-2026-08-amer-aborted-0001`
- Successful rerun: `job-2026-08-amer-rerun-0002`

All six regional jobs now show `COMPLETED`. A completed scheduler status does not
prove every candidate record succeeded; job-level data-failure detail is needed
for exact failed IDs.

## Conclusion — three contributors

1. **Recently-ended inactives** inflate the broad eligible baseline and account
   for at least 1,450 unnotified records (expected, not a failure).
2. **Query parity:** the monitoring query is not equivalent to the runtime query,
   most importantly the missing `eligible_record_types` filter (~230 overcounted).
3. **Aborted-then-rerun AMER job:** record-level failures or checkpoint behavior
   may explain some active contracts that still carry null or old dates.

**Exact next step:** obtain the runtime `eligible_record_types` values (done above)
and the job data-failure output, then compare the frozen pre-job contract IDs to
the notified contract IDs.

## Why this is an agent problem

Each contributor above is a *reason code* the agent already models: recently-ended
grace (`expected_non_send`), query-parity overcount (a monitoring artifact, not a
miss), and a genuine job failure (`real_failure` / `needs_review`). The value of
the agent is separating the ~230 + 1,450 expected/overcounted records from the
genuinely missed ones so an analyst chases only what's real.
