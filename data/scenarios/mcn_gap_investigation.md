# MCN Multiplier-Notice Gap Investigation (worked example)

> **SYNTHETIC / ANONYMIZED.** Every number, identifier, product name, and config
> value below is fabricated for the demo. This document reproduces the *shape* of
> a real quarterly multiplier-notification gap investigation — it contains no real
> customer, contract, or company data.

Multiplier-change notices (MCN) run on a **quarterly** cadence, not monthly. That
single fact changes how a gap must be read: for most of the quarter the "sent"
count is legitimately zero because the send window has not opened yet. The
assurance agent has to tell *"the run hasn't happened"* apart from *"the run
happened and skipped these records."*

## Apparent gap

A monitoring query returns **9,400** entitlements that are eligible for a
multiplier notice this quarter but carry no multiplier-notification date. On a
monthly process that would look alarming. On MCN it usually is not.

### First question: has this quarter's run fired?

| Signal | Value | Reading |
|---|---|---|
| Eligible entitlements | 9,400 | large open queue |
| Stamped this quarter | 0 | **no send has run yet** |
| Days into quarter | 12 | send window opens later |

Because **0 of 9,400** are stamped, this is a **notification-run-pending** state,
not a delivery failure. The correct agent behavior is to report "run pending" and
defer reconciliation — *not* to raise 9,400 escalations. Flagging a whole eligible
population as missed the day before the scheduled send is the classic
false-positive this cadence invites.

## After the run: the real gaps

Once the quarterly send completes, the same query returns a much smaller residue —
say **210** eligible-but-unstamped entitlements. These split into three causes the
agent separates:

### 1. Throttle-window suppression (expected non-send)

The multiplier process will not re-notify an entitlement stamped within the last
~80 days. An entitlement stamped **47 days ago** still shows as "eligible this
quarter" in a naive query but is legitimately inside the throttle window.

```
last_multiplier_notified within the last ~80 days  ->  skip re-send (expected)
```

These are **not** misses. The agent excludes them as compliant non-sends.

### 2. Multiplier not yet effective (out of window)

Eligibility also depends on the multiplier change taking effect soon. An
entitlement whose multiplier change is dated next quarter is correctly not
notified this quarter — another expected non-send.

### 3. Genuine miss (the residue that matters)

What remains — active, subscribed, in-window, past the throttle, but never
stamped — is a **genuine miss**. This is the small, high-value population the
analyst should chase, and the only slice that should escalate.

## What the agent concludes

- Before the run: **"notification run pending"** — reconciliation deferred, zero
  escalations.
- After the run: throttle-window and not-yet-effective records **excluded** as
  expected non-sends; only the genuine residue is escalated with evidence.

The lesson MCN teaches the design: **reconciliation must be cadence-aware.** The
same eligible-minus-stamped arithmetic that is right for a monthly process
produces a massive false positive on a quarterly one if you ignore whether the
send has actually run.
