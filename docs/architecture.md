# Rewrite Architecture

## Layers

### Engine

`src/engine/` contains use cases, permission rules, and port validation. The engine knows nothing about HTTP, filesystems, or a concrete database.

### Adapters

`src/adapters/` contains implementation details for the engine ports. The rewrite currently ships:

- an in-memory adapter for fast tests and demo startup
- a JSON-file adapter for single-instance durable state
- a normalized PostgreSQL adapter for hosted durable state
- a Cloud SQL connector bootstrap path for Cloud SQL for PostgreSQL

### HTTP Interface

`src/interfaces/http/` contains the API server and request/response mapping. It is intentionally thin: it parses HTTP details, delegates to the engine, and translates engine errors back to status codes.

### Static Admin

`frontend/admin/` is a standalone static site. It carries its own API base-url configuration and authenticates with a single login call that yields a bearer token for subsequent requests.

## Current Workflows

- Staff can create members, review sponsored applications, create and issue invoices, record manual payments, and record donations.
- Member-self accounts can only prepay dues, donate, cancel their own membership, and submit sponsored applications.
- Financial summaries are computed from stored invoices, payments, and donations rather than hard-coded report fixtures.
- Account credentials are stored as password hashes, not raw passwords.
- Sessions expire and can be explicitly revoked through logout.

## Near-Term Follow-On ADRs

- Stripe and Every.org provider adapters
- role policy expansion for narrower staff roles
- background cleanup for expired sessions and operational housekeeping
- write-path use cases for expenses, exports, access control, and reconciliation

## ADR Roadmap

- ADR 0006 established the engine, versioned HTTP API, static admin shell, and repository-port boundary.
- ADR 0007 added JSON-file durability and the first operational write workflows.
- ADR 0008 added hosted PostgreSQL document persistence, password hashing, and bootstrap credential configuration.
- ADR 0009 replaced PostgreSQL document storage with normalized tables, added session expiry and revocation, and added Cloud SQL connector runtime construction.
- ADR 0010 aligned repository practices, documentation layers, test scripts, and coverage exception tracking with the active project standards.
