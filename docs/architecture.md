# Rewrite Architecture

## Layers

### Engine

`src/engine/` contains use cases, permission rules, and port validation. The engine knows nothing about HTTP, filesystems, or a concrete database.

### Adapters

`src/adapters/` contains implementation details for the engine ports. The rewrite currently ships:

- an in-memory adapter for fast tests and demo startup
- a JSON-file adapter for single-instance durable state

### HTTP Interface

`src/interfaces/http/` contains the API server and request/response mapping. It is intentionally thin: it parses HTTP details, delegates to the engine, and translates engine errors back to status codes.

### Static Admin

`frontend/admin/` is a standalone static site. It carries its own API base-url configuration and authenticates with a single login call that yields a bearer token for subsequent requests.

## Current Workflows

- Staff can create members, review sponsored applications, create and issue invoices, record manual payments, and record donations.
- Member-self accounts can only prepay dues, donate, cancel their own membership, and submit sponsored applications.
- Financial summaries are computed from stored invoices, payments, and donations rather than hard-coded report fixtures.

## Near-Term Follow-On ADRs

- networked database adapter selection and migration strategy
- durable token/session expiry and revocation
- Stripe and Every.org provider adapters
- role policy expansion for narrower staff roles
- write-path use cases for expenses, exports, access control, and reconciliation
