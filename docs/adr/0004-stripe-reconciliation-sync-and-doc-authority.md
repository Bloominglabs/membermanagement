# ADR 0004: Stripe Reconciliation Sync and Documentation Authority

## Status

Accepted

## Context

Stripe reconciliation is still only a reporting stub in the current codebase:

- succeeded Stripe payments are counted as "pending reconciliation" when `processor_balance_txn_id` is blank
- the scheduled task and management command report that count, but they never pull Stripe balance transaction identifiers back into local payment records
- staff can trigger a reconciliation check, but not an actual synchronization step

At the same time, the documentation set is still harder to navigate than it should be:

- the root README lists current, reference, and historical docs together without a clear authority model
- the Google Sheets handoff remains in the tree even though it is historical only
- the current Stripe/payment spec still contains raw citation markers from the research synthesis process

## Decision

Implement a first real Stripe reconciliation pass and clean up documentation authority at the same time.

### Stripe reconciliation

Add a Stripe reconciliation sync service that:

1. selects succeeded Stripe payments missing `processor_balance_txn_id`
2. retrieves the latest Stripe PaymentIntent or Charge state
3. backfills `processor_charge_id` and `processor_balance_txn_id` when Stripe provides them
4. returns a structured summary for command, task, and staff-UI reporting

This remains intentionally narrow: it is a balance-transaction backfill step, not a full payout or fee ledger subsystem.

### Documentation cleanup

Clarify doc authority by:

1. adding a docs index that distinguishes current, reference, and historical documents
2. updating the root README to point to that index instead of treating every doc as equally current
3. marking historical/reference docs explicitly
4. removing citation artifacts from the current `docs/spec.md`

## Consequences

### Positive

- Stripe reconciliation becomes an actual sync path rather than a count-only placeholder
- staff and operators get meaningful reconciliation summaries
- the docs set becomes easier to use without guessing which file is authoritative
- the current spec becomes readable as project documentation instead of raw research output

### Negative

- reconciliation still does not model Stripe fees, payouts, disputes, or bank matching as first-class local records
- the docs index adds another file that must stay aligned as the doc set evolves

## Success Criteria

- succeeded Stripe payments can be backfilled with `processor_balance_txn_id` from Stripe data
- the reconciliation command and task use the sync service rather than count-only reporting
- staff-triggered reconciliation reports a sync summary
- the docs clearly distinguish current, reference, and historical materials
- `docs/spec.md` no longer contains raw citation markers
