# MAS Monitoring — Data Model & Methodology

> **SYNTHETIC / ANONYMIZED.** Field names, URLs, job names, and volumes are
> fabricated for the demo. This describes the *methodology* of a statement-period
> monitoring dashboard without any real company or customer data.

## Purpose

Monitor the Monthly Account Statement (MAS) process using a **bank-statement-style
view**: each dashboard row represents the *month of statement activity*, not the
month the notification was delivered.

- A June statement stays in the June row even though notifications went out in
  early July.
- A July statement stays in the July row even though notifications are scheduled
  for August.

## Data model

Display **contracts and entitlements separately** — entitlement counts must never
be labeled as unique contract counts. For each statement period preserve:

- eligible contracts / eligible entitlements
- notified (sent) contracts / notified entitlements
- missing contracts / missing entitlements
- delivery rate (sent ÷ eligible against a **frozen** baseline)
- snapshot date, delivery date (or scheduled delivery date), environment, status

Before the notification job runs, zero sent means **`Awaiting notification run`**,
not failure.

## Notification source of truth

The source system keeps **no separate delivery-log object**. When a statement email
is sent, the contract's `last_statement_notified` date field is stamped. That stamp
is the *only* proof-of-send:

```
SELECT id, contract_number, last_statement_notified
FROM   contract
WHERE  last_statement_notified within [delivery-month start, next-month start)
```

- Count **unique contract IDs** for the sent-contract metric.
- For sent entitlements, count eligible entitlements whose parent contract has a
  notification date inside the delivery window.
- After a month closes, use an **explicit date range** (not "this month") for
  reproducible historical reporting — e.g. a July statement delivered in August:

```
WHERE last_statement_notified >= 2026-08-01
  AND last_statement_notified <  2026-09-01
```

## Frozen baseline rule

Do **not** replace the pre-job eligible baseline with a post-job eligibility count
— eligible records can drop after notification (e.g. entitlements that end). Keep
both the pre-job baseline and the actual delivery numbers in the same
statement-period row so the delivery rate stays meaningful.

## Regional completion

Notifications run as six regional jobs. Do not treat the overall run as complete
until all six report `COMPLETED`; a `RUNNING` region explains a partial delivery
rate, and stamped totals should keep rising until every region finishes.

Synthetic regional job names:

- `statement-notify-amer`
- `statement-notify-emea`
- `statement-notify-apac`
- `statement-notify-japan`
- `statement-notify-canada`
- `statement-notify-latam`

A machine-readable scheduler status would live at a placeholder endpoint such as
`https://scheduler.internal.example.com/schedules`.

## Automation (illustrative)

An hourly local job (`com.example.mas-hourly-refresh`) could re-query the
delivery-month totals while processing continues, logging to `hourly_refresh.log`.
This is illustrative only — the demo ships static synthetic reports instead.

## Dashboard expectations

- Default environment label: `demo` (synthetic).
- A statement-periods table with separate rows per statement month.
- Statement period and delivery period are separate columns.
- The latest statement period drives the headline cards.
- A period shows `Awaiting notification run` until post-job validation is done.

See `data/sample_reports/statement_periods.json` for the synthetic dataset the
demo dashboard renders.
