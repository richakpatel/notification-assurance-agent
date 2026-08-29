# MCN (Multiplier Change Notification) Eligibility & Handling — SYNTHETIC / QA ONLY

## Eligibility: who should receive a multiplier notice
notification_type: MCN
reason_code: eligibility_rule
A record is eligible for the multiplier notice when the entitlement and contract are
active, it is subscribed to multiplier notifications, a multiplier change is
effective soon (within the notice window), and the account is not suppressed for
multiplier notices. Unlike the monthly statement, the "already sent" guard is a
THROTTLE: a record is skipped if it was stamped within the throttle window (about 80
days), not merely this calendar month.

## Missed: eligible but not stamped within the window
notification_type: MCN
reason_code: eligible_not_stamped
When a record is eligible but has no multiplier stamp inside the current cycle
window, the multiplier notice was not confirmed sent. Recommended action: probe the
external provider; re-run if no send occurred. Note MCN update failures are recorded
in a generic error log, so cross-check that log when investigating.

## Throttle nuance
notification_type: MCN
reason_code: throttle_window
Because MCN uses a throttle rather than a month boundary, a record stamped late in a
prior window may legitimately be skipped this cycle. Do not treat a within-throttle
skip as missed.
