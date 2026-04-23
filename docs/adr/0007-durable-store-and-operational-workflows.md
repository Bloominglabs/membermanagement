# ADR 0007: Durable Store and Operational Workflows

## Status

Accepted

## Context

ADR 0006 established the rewrite boundaries but only with in-memory read paths. That is not enough for deployment. The suite must persist state across restarts and support the operational workflows that define the actual product:

- staff member management
- sponsored application intake and review
- invoice creation and issuance
- manual and self-service payment capture
- donation recording
- member cancellation
- financial summary reads based on stored transactions

The rewrite must keep those workflows inside the engine so that HTTP remains an adapter, not the source of business rules.

## Decision

The next slice will add:

- a durable JSON-file adapter for repository-backed persistence
- engine use cases for members, applications, invoices, payments, donations, and cancellations
- explicit authorization rules for staff-admin and member-self roles
- HTTP endpoints for those use cases
- a modest expansion of the static admin client so the new write paths are exercisable without server-rendered UI

The durable adapter is an interim deployment path, not the final database story. It proves that the rewrite works against persisted state while preserving the repository boundary needed for a later SQL adapter.

## Consequences

### Positive

- The rewrite can support real workflows rather than read-only demonstrations.
- Persistence is available without adding database packages prematurely.
- The repository boundary remains intact, which keeps the path open for PostgreSQL or another durable store later.

### Negative

- A JSON-file adapter is not the final concurrency or scale answer.
- Report computation will initially be derived in-process from stored records rather than delegated to a reporting database.
- Production deployment on platforms without persistent filesystem support still requires a follow-on durable adapter.

## Success Criteria

- State survives process restarts when backed by the JSON-file adapter.
- Staff can create members, record applications, create and issue invoices, record manual payments, and record donations.
- Member-self accounts can only prepay dues, donate, cancel themselves, and submit sponsored applications.
- The financial summary reflects issued invoices, applied payments, prepaid credit, and donations.

