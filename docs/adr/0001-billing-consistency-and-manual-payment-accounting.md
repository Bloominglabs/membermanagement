# ADR 0001: Billing Consistency and Manual Payment Accounting

## Status

Accepted

## Context

The project already treats Bloominglabs as the ledger of record, but several billing paths are inconsistent:

- Stripe checkout requests do not net out existing member credit before asking for payment.
- Stripe request idempotency is attached with an `options` payload rather than Stripe's request-option keys.
- Manual payment intake through the API bypasses the same allocation, posting, and member-status flow used by the staff UI.
- Payment allocation accepts invoices that should not be allocatable, such as drafts or records outside the payment's billing scope.
- Member status transitions treat any open receivable as past due, even before the invoice due date.

These inconsistencies create accounting drift between staff workflows, API workflows, and Stripe-backed workflows.

## Decision

Implement a single consistency pass across billing intake and allocation:

1. Stripe payment creation paths must send top-level `idempotency_key` request options.
2. Stripe "pay balance" checkout must charge only the member's net amount due after existing credit is applied.
3. Manual payment entry must use the same service path regardless of whether it originates from the staff UI or API.
4. Allocation must reject draft, void, and out-of-scope invoices instead of silently attaching money to them.
5. Member status updates must distinguish "invoice exists" from "invoice is overdue".

## Consequences

### Positive

- Offline and escape-hatch payments are journaled and status-adjusting in the same way as digital payments.
- Stripe retries are less likely to create duplicate payment intents or checkout sessions.
- Staff and API allocation behavior becomes predictable and safer.
- Member status reflects lateness rather than merely having an issued invoice.

### Negative

- Some previously accepted allocation requests will now fail fast.
- Existing tests that relied on the old behavior must be updated to reflect the stricter contract.

## Success Criteria

- Regression tests cover the new behavior before the implementation lands.
- Manual payments entered through the API create the same accounting side effects as manual payments entered through the staff UI.
- "Pay balance" checkout only requests the net outstanding amount.
- Allocation rejects non-allocatable invoices.
- Members with not-yet-due invoices remain non-past-due.
