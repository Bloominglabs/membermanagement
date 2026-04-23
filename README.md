# Bloominglabs Member Management Rewrite

This branch replaces the legacy Django monolith with a package-light JavaScript architecture built around a core management engine, explicit repository and provider ports, a thin HTTP API, and a static admin client.

## Branches

- `legacy-django-monolith`: frozen reference for the prior Django/Postgres implementation and its supporting docs.
- `adr-0006-engine-static-admin-rewrite`: the new architecture branch started from a clean orphan history.

## Current Scope

The rewrite now establishes:

- a core engine with explicit authentication, authorization, and workflow use cases
- in-memory and durable JSON-file repository adapters
- a thin HTTP API adapter exposing health, login, staff operations, member self-service operations, and financial-summary reads
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
3. Run `DATA_FILE_PATH=var/data/store.json npm start` for durable local testing, or `npm start` for demo mode.
4. Open `http://127.0.0.1:3000/`.

The working practices for this rewrite live in [`development-practices.md`](development-practices.md).

The seed admin login for the first scaffold is `admin` / `change-me`.

## Implemented API Surface

- `POST /api/v1/session/login`
- `GET /api/v1/members`
- `POST /api/v1/members`
- `GET /api/v1/applications`
- `POST /api/v1/applications/:id/review`
- `POST /api/v1/invoices`
- `POST /api/v1/invoices/:id/issue`
- `POST /api/v1/payments/manual`
- `POST /api/v1/donations`
- `POST /api/v1/self/prepayments`
- `POST /api/v1/self/donations`
- `POST /api/v1/self/cancellation`
- `POST /api/v1/self/sponsored-applications`
- `GET /api/v1/reports/financial-summary`

Deployment-specific notes are in [`docs/deployment.md`](docs/deployment.md).
