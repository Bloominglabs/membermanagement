# Bloominglabs Member Management

Self-hosted Django/Postgres membership, billing, donations, reporting, and RFID allowlist system for a makerspace.

## What is implemented

- Django modular monolith under [`backend/`](backend/)
- Domain apps for members, billing, donations, ledger, expenses, access, and audit
- DRF endpoints for client/member CRUD, balances, invoice schedules, expense categorization rules, manual payments, Stripe session/setup-intent creation, webhooks, access snapshots, and financial reports
- FIFO payment allocation, dues invoice generation, member status enforcement, and basic journal posting
- Thin staff operations UI under `/staff/` for member, billing, donations, expenses, access, reports, and audit workflows
- On-prem access-agent stub under [`onprem/access_agent/`](onprem/access_agent/)
- Docker/Compose scaffolding under [`infra/`](infra/)
- Pytest coverage for the core financial and webhook rules
- Authenticated management API, access-agent key auth for door-access endpoints, and a public [`/healthz`](backend/config/urls.py) health check

## Local run

1. Install the Python dependencies from [`requirements.txt`](requirements.txt).
2. Run `PYTHONPATH=.pkg:backend python3 backend/manage.py migrate`
3. Run `PYTHONPATH=.pkg:backend python3 backend/manage.py runserver`
4. Run tests with `PYTHONPATH=.pkg:backend python3 -m pytest -q`

## Deployment

For local development, run the core stack plus [`infra/docker-compose.dev.yml`](infra/docker-compose.dev.yml).

For the actual Treasurer-facing deployment, run the core stack plus [`infra/docker-compose.prod.yml`](infra/docker-compose.prod.yml) with [`infra/prod.env.example`](infra/prod.env.example) as the template for real secrets. The deployment recommendation and rollout steps are in [`docs/qa-hosting.md`](docs/qa-hosting.md).

## Key assumptions

- Relevant project documentation now lives under [`docs/`](docs/). Start with the documentation index at [`docs/README.md`](docs/README.md), which distinguishes current authority docs from reference and historical material.
- The shared ChatGPT conversation was not retrievable from this environment, so any requirements unique to that conversation still need to be folded in once you provide accessible text.
