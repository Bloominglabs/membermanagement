# ADR 0009: Normalized PostgreSQL, Session Lifecycle, and Cloud SQL Connector

## Status

Accepted

## Context

ADR 0008 made hosted persistence possible, but the PostgreSQL adapter still stores the entire application state as a single document. That blocks safe multi-step updates, limits database-level visibility, and leaves Cloud SQL deployment partly external to the codebase. Session handling is also still too weak for deployment because issued tokens do not expire and cannot be revoked.

## Decision

The next slice will:

- replace the document-style PostgreSQL persistence layer with normalized tables for the current operational workflows
- add session expiry and revocation, plus a logout endpoint
- add transaction boundaries around the engine's multi-step write workflows when the adapter supports them
- add a Cloud SQL Node.js Connector path for Google Cloud SQL for PostgreSQL deployments

The file and in-memory adapters remain in place for local development and test speed, but PostgreSQL becomes the primary hosted adapter.

## Consequences

### Positive

- Hosted deployments gain a more appropriate relational persistence layer.
- Session tokens become time-bounded and revocable.
- Cloud Run to Cloud SQL connectivity is represented in code rather than only in external deploy notes.

### Negative

- The repository and runtime wiring become more complex because transactional scopes must be supported.
- The normalized schema still covers only the currently implemented workflows, not the entire future system.

## Success Criteria

- PostgreSQL persistence uses normalized tables rather than a single document row.
- Session tokens expire and are rejected after logout.
- The runtime can build a PostgreSQL pool through the Cloud SQL Node.js Connector using environment configuration.

