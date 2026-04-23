# AAR 0009: Normalized PostgreSQL, Session Lifecycle, and Cloud SQL Connector

## Outcome

ADR 0009 succeeded. The rewrite now supports:

- normalized PostgreSQL persistence for the currently implemented workflows
- transactional write scopes for the PostgreSQL adapter
- expiring and revocable bearer-token sessions
- a logout endpoint and matching static-admin logout flow
- Google Cloud SQL connector bootstrap for Cloud SQL for PostgreSQL

## What Worked

- The repository-port boundary made it possible to move PostgreSQL from document storage to normalized tables without changing the external API surface.
- Session lifecycle controls fit cleanly into the engine once the session repository contract gained revocation.
- The Cloud SQL connector path was straightforward to validate by isolating pool construction behind bootstrap helpers.

## Remaining Gaps

- The normalized schema only covers the workflows already rebuilt on this branch.
- Session expiry is enforced, but expired-session cleanup is not yet batched or scheduled.
- Third-party provider adapters for Stripe and Every.org still need to be reintroduced on the rewrite branch.

