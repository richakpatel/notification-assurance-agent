# Threshold Notification Eligibility & Handling — SYNTHETIC / QA ONLY

## Eligibility: which usage rows should notify today
notification_type: THRESHOLD
reason_code: eligibility_rule
A usage row is eligible when usage has crossed a configured tier (80, 90, or 100
percent), the entitlement subscribes to that tier, the entitlement is active, and the
crossed tier is NOT already present in the row's sent-tier list. Only the highest
crossed tier that has not yet been sent triggers a notification. The sent-tier list is
a semicolon-style list rebuilt each run.

## Missed: crossed a tier but tier not in the sent list
notification_type: THRESHOLD
reason_code: eligible_not_stamped
When usage crossed a subscribed tier this cycle but that tier is absent from the sent
list, the threshold notice was not confirmed sent. Probe the external provider and
re-run if needed.

## High-severity gap: silent stamp failure
notification_type: THRESHOLD
reason_code: threshold_silent_failure
The threshold process only writes a debug line if its sent-list update fails -- it
does not raise a system error alert or an error-log record. So an email can go out while the
tier is never recorded, or the update can fail invisibly. If the external provider
shows a delivery but the tier is missing from the sent list, classify this as a
high-severity silent failure and route for human review; it indicates lost
proof-of-send that the source system cannot detect on its own.

## Reset behavior
notification_type: THRESHOLD
reason_code: threshold_reset
A separate reset process removes a tier from the sent list when usage drops back
below it, so a later re-crossing re-triggers a notice. A tier legitimately absent
because usage fell is not a missed notification.
