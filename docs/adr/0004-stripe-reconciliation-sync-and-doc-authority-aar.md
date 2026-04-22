# AAR 0004: Stripe Reconciliation Sync and Documentation Authority

## Decision Reviewed

[ADR 0004](./0004-stripe-reconciliation-sync-and-doc-authority.md)

## Immediate Outcome

The repository now has a real first-pass Stripe reconciliation sync and a clearer documentation map:

- succeeded Stripe payments missing `processor_balance_txn_id` can now be backfilled from Stripe PaymentIntent and Charge lookups
- the reconciliation management command, Celery task, and staff billing action now use the sync service and report structured results
- the current documentation set now has an explicit index and authority model
- the current `docs/spec.md` has been cleaned of research-era citation markers

## Evidence

- targeted unit coverage was added for PaymentIntent-based reconciliation, Charge fallback reconciliation, and the not-configured path
- the full regression suite passes after the reconciliation and docs cleanup changes
- `manage.py check` passes after the command and staff billing wiring changes

## Follow-Up

- extend reconciliation beyond balance-transaction backfill if the project needs fee, payout, dispute, and bank-match visibility as first-class records
- keep the docs index updated as new ADRs and operational docs are added
- decide later whether the research memo should be fully normalized or left as a reference artifact
