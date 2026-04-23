# AAR 0007: Durable Store and Operational Workflows

## Outcome

ADR 0007 succeeded. The rewrite now supports:

- durable JSON-file persistence
- staff member creation
- sponsored application submission and review
- invoice creation and issuance
- manual payment capture with invoice allocation and prepaid-credit carryover
- donation recording
- member self-service prepayment, donation, cancellation, and sponsored-application submission

## What Worked

- Sharing one document-runtime adapter layer between in-memory and file-backed modes kept the engine contract stable.
- Deriving financial summaries from stored invoices, payments, and donations verified that the rewrite can own operational state without a reporting sidecar.
- Keeping self-service permissions explicit in the engine reduced the chance of accidentally exposing staff-only workflows.

## Remaining Risks

- The JSON-file adapter is not a long-term concurrency answer.
- Sessions are persisted, but there is not yet a revocation or expiry policy.
- Deployment on Cloud Run still needs a non-filesystem durable adapter for production use.

