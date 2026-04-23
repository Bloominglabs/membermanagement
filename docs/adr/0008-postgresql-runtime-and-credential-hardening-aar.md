# AAR 0008: PostgreSQL Runtime and Credential Hardening

## Outcome

ADR 0008 succeeded. The rewrite now supports:

- hosted persistence through a PostgreSQL-backed state store
- runtime selection based on `DATABASE_URL`
- hashed account credentials instead of plaintext password storage
- configurable bootstrap admin credentials for first-run seeding

## What Worked

- The document-runtime boundary made it possible to add a hosted adapter without changing the engine workflow surface.
- Built-in Node crypto primitives were sufficient for password hashing, so no extra security package was required.
- `pg-mem` provided enough parity to exercise the PostgreSQL path in automated tests.

## Remaining Caveat

- The PostgreSQL adapter still persists the application state as one document and multi-step workflows are not yet wrapped in broader transactional units. For hosted deployment today, the service should run with a single application instance until the normalized SQL adapter lands.

