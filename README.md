# Bloominglabs Member Management Rewrite

This branch replaces the legacy Django monolith with a package-light JavaScript architecture built around a core management engine, explicit repository and provider ports, a thin HTTP API, and a static admin client.

## Branches

- `legacy-django-monolith`: frozen reference for the prior Django/Postgres implementation and its supporting docs.
- `adr-0006-engine-static-admin-rewrite`: the new architecture branch started from a clean orphan history.

## Current Scope

The first rewrite slice establishes:

- a core engine with explicit authentication, authorization, and read use cases
- in-memory repository adapters so the architecture is testable before a database choice is finalized
- a minimal HTTP API adapter exposing health, login, member listing, and financial summary reads
- a static admin client that authenticates once and then uses a bearer token for subsequent API requests

## Architectural Direction

- The backend is a self-contained application layer with no server-rendered HTML dependency.
- Authorization decisions live in the engine, not only in HTTP route handlers.
- Database modularity is expressed through repository ports rather than ORM-coupled service code.
- Third-party integrations are modeled as provider ports so Stripe and Every.org can be replaced or stubbed cleanly.
- The admin UI is a static site that can be hosted separately from the engine.

## Development

1. Install Node.js 18 or newer.
2. Run `npm test`.
3. Run `npm start`.
4. Open `http://127.0.0.1:3000/`.

The working practices for this rewrite live in [`development-practices.md`](development-practices.md).

The seed admin login for the first scaffold is `admin` / `change-me`.
