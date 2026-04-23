# ADR 0008: PostgreSQL Runtime and Credential Hardening

## Status

Accepted

## Context

ADR 0007 made the rewrite operational for single-instance testing, but it still has two deployment blockers:

- the durable adapter is filesystem-based, which is a poor fit for Cloud Run and other stateless container platforms
- accounts still rely on plaintext password storage, which is not acceptable for deployment

The next deployment-oriented slice must therefore provide:

- a networked persistence adapter suitable for managed PostgreSQL
- password hashing and verification that remove raw-password persistence from the runtime state

## Decision

The rewrite will add:

- a PostgreSQL-backed state store using the existing document-runtime boundary
- runtime selection logic that prefers PostgreSQL when `DATABASE_URL` is configured
- password hashing and verification using built-in Node crypto primitives
- test coverage for PostgreSQL parity using an in-memory PostgreSQL-compatible test harness

This preserves the repository and adapter boundary while giving the project a hosted deployment path before the final normalized SQL schema is designed.

## Consequences

### Positive

- Hosted deployments can use managed PostgreSQL instead of local files.
- Credentials are no longer stored as raw passwords.
- Existing engine workflows can move to PostgreSQL without rewriting the engine layer.

### Negative

- The PostgreSQL adapter still persists the application state as a single document row rather than a normalized relational model.
- Concurrency characteristics improve over the filesystem adapter but are not the final persistence design.

## Success Criteria

- Runtime bootstrap selects PostgreSQL when `DATABASE_URL` is present.
- Default and persisted account state contains password hashes, not plaintext passwords.
- The PostgreSQL runtime passes the same operational workflow expectations as the file-backed runtime.

