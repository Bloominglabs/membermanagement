# Rewrite Architecture

## Layers

### Engine

`src/engine/` contains use cases, permission rules, and port validation. The engine knows nothing about HTTP, filesystems, or a concrete database.

### Adapters

`src/adapters/` contains implementation details for the engine ports. The first adapter is in-memory only so the rewrite can prove the boundaries before selecting a persistent store.

### HTTP Interface

`src/interfaces/http/` contains the API server and request/response mapping. It is intentionally thin: it parses HTTP details, delegates to the engine, and translates engine errors back to status codes.

### Static Admin

`frontend/admin/` is a standalone static site. It carries its own API base-url configuration and authenticates with a single login call that yields a bearer token for subsequent requests.

## Near-Term Follow-On ADRs

- database adapter selection and migration strategy
- durable token/session storage
- Stripe and Every.org provider adapters
- role policy expansion for self-service member actions and narrower staff roles
- write-path use cases for membership, invoices, and payments

