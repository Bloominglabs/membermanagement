# ADR 0006: Engine, API, and Static Admin Rewrite

## Status

Accepted

## Context

The prior implementation grew into a Django monolith that mixed domain rules, database access, HTTP concerns, and staff UI rendering in the same runtime. That shape makes it hard to:

- host the backend on platforms such as Cloud Run without carrying server-rendered UI concerns
- host the admin interface as a static site
- change database implementations without rewriting business logic
- enforce authorization consistently across interfaces

The new target architecture is:

- a core management engine that owns membership state, billing rules, reporting, and authorization
- repository ports that abstract persistence behind explicit interfaces
- provider ports for Stripe, Every.org, and other external systems
- a thin HTTP API adapter
- a static admin client that authenticates over HTTPS and then uses issued tokens, not raw passwords on every request

## Decision

The rewrite will begin from a clean branch in plain JavaScript with minimal dependencies.

The first implementation slice will:

- define engine ports for accounts, members, reports, and session tokens
- keep authorization decisions inside the engine use cases
- ship an in-memory adapter set so the engine can be verified without committing to a concrete database
- expose a versioned HTTP API under `/api/v1/`
- serve a static admin client only as a development convenience; the client will remain deployable to a static host

## Consequences

### Positive

- The domain layer becomes testable without HTTP or database coupling.
- Hosting options widen because the backend becomes an API service rather than an HTML-rendering application.
- Static hosting for the admin client becomes straightforward.
- The rewrite can add database adapters incrementally without reworking use-case logic.

### Negative

- The initial rewrite will temporarily have less feature coverage than the legacy branch.
- Some convenience features from the monolith must be rebuilt intentionally.
- Operational concerns such as persistent session stores and production database adapters will arrive in later ADRs.

## Success Criteria

- Engine use cases run against in-memory repositories and pass without HTTP involvement.
- The API exposes login plus authenticated reads for members and reports.
- The admin client is static and does not depend on same-origin server sessions or template rendering.
- Future database work can be expressed as adapter additions rather than engine rewrites.

