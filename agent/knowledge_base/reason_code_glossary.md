# Reason-Code Glossary — SYNTHETIC / QA DATA ONLY

## eligible_not_stamped
reason_code: eligible_not_stamped
category: real_failure
A record was eligible this cycle but carries no proof-of-send stamp. Because the
stamp is the only proof-of-send, this is the core missed-notification case. Counts as
missed; probe the external provider and re-run if no send occurred.

## suppressed
reason_code: suppressed
category: expected_non_send
A compliant, expected non-delivery caused by an account-level suppression flag.
Excluded from missed counts. No follow-up task. No escalation.

## throttle_window
reason_code: throttle_window
category: expected_non_send
A record legitimately skipped because it was stamped within the notification throttle
window (multiplier notices). Not a missed notification.

## threshold_reset
reason_code: threshold_reset
category: expected_non_send
A threshold tier is absent from the sent list because usage dropped back below it and
the reset process cleared it. Not a missed notification.

## threshold_silent_failure
reason_code: threshold_silent_failure
category: needs_review
Usage crossed a subscribed tier and the external provider shows a delivery, yet the
tier is missing from the sent list. The threshold process only debug-logs update
failures, so this proof-of-send loss is invisible to the source system. High
severity; route for human review.

## stamped_but_bounced
reason_code: stamped_but_bounced
category: needs_review
A record is stamped as sent, but an external delivery probe shows the message bounced
or was not delivered. Invisible to the source system because the stamp is the only
internal proof-of-send. High severity; route for human review and re-send.

## integrity_mismatch
reason_code: integrity_mismatch
category: needs_review
The two independent signals disagree (stamp vs. external delivery probe). A
data-quality signal, not a normal outcome. Route for human review.

## unknown
reason_code: unknown
category: needs_review
No runbook or glossary entry adequately explains the observed state, or retrieval
confidence was below threshold. Routed to a human analyst rather than auto-classified.
Analyst corrections are stored in long-term memory to improve future classification.
