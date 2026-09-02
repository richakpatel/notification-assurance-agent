# MAS (Monthly Account Statement) Eligibility & Handling — SYNTHETIC / QA ONLY

## Eligibility: who should receive MAS this month
notification_type: MAS
reason_code: eligibility_rule
A record is eligible for the monthly statement when ALL hold: the entitlement is
active (or ended within the last 45 days); it is subscribed to monthly statements
(monthly-usage subscription plus a customer/reseller recipient type); the contract
started on or before last month; and the account is NOT suppressed for statement
notifications. Eligible records that have already been stamped for the current month
are excluded from the run -- the monthly stamp is the "already sent" guard.

## Missed: eligible but not stamped this month
notification_type: MAS
reason_code: eligible_not_stamped
When a record is eligible this month but its statement stamp is empty or from a
prior month, the statement was not confirmed sent. This is the core missed case.
Recommended action: confirm whether an email actually went out (external provider
probe). If it did not, re-run the statement for that record; if it did, treat as a
lost proof-of-send (see integrity runbook).

## Excluded: suppressed account
notification_type: MAS
reason_code: suppressed
When the account is suppressed for statement notifications, a non-send is expected
and compliant. Exclude from the missed count. Do not escalate.
