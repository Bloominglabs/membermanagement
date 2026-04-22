# AAR 0001: Billing Consistency and Manual Payment Accounting

## Decision Reviewed

[ADR 0001](./0001-billing-consistency-and-manual-payment-accounting.md)

## Immediate Outcome

The billing stack now behaves more consistently across staff, API, and Stripe-backed flows:

- manual payments entered through the API follow the same posting and status-update path as staff-entered manual payments
- Stripe checkout and autopay requests now carry request-level idempotency keys
- "pay balance" checkout uses net receivable after existing credit
- allocation rejects draft, void, and out-of-scope invoices
- not-yet-due invoices no longer mark a member as past due
- monthly dues close auto-applies prepaid credit without guessing how to re-route every historical payment

## Evidence

- focused regression suite added for billing consistency and manual-payment accounting
- existing failing billing tests now pass alongside the new regression tests

## Follow-Up

- add API-level tests for rejected allocation requests so the HTTP contract is explicit, not only the service contract
- decide whether the staff UI should expose more manual-payment fields such as received date and structured reference numbers for checks or transfers
- revisit this AAR after real operator usage to see whether additional allocation tooling is needed
