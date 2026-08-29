# Data-Integrity Cross-Check Runbook — SYNTHETIC / QA DATA ONLY

## Cross-check: stamp vs. external delivery probe
notification_type: ANY
reason_code: integrity_mismatch
The source system keeps NO separate delivery-log object: the stamp field on the
record (statement date, multiplier date, or threshold sent-list) is the only internal
proof-of-send. The agent therefore cross-checks the stamp against an EXTERNAL
delivery probe (email/event provider). Two directions of mismatch:

- Stamped but the probe shows a bounce/non-delivery: the send was recorded as
  successful while the customer was not actually reached. See stamped_but_bounced.
- Delivered per the probe but no stamp for this cycle: the notification reached the
  customer while the record was never marked, so downstream logic still believes the
  customer was not notified. For threshold this is especially likely because its stamp
  update failures are only debug-logged. See threshold_silent_failure.

Both directions are data-quality signals, not normal delivery outcomes, and must be
routed for human review (needs_review). They are the class of failure the source
system cannot detect on its own, which is where this assurance agent adds value.
