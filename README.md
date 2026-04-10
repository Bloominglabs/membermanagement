# Bloominglabs Member Management

Self-hosted Django/Postgres membership, billing, donations, reporting, and RFID allowlist system for a makerspace.

## What is implemented

- Django modular monolith under [`backend/`](/home/jpt4/constructs/blbs/membermanagement/backend)
- Domain apps for members, billing, donations, ledger, expenses, access, and audit
- DRF endpoints for client/member CRUD, balances, invoice schedules, expense categorization rules, manual payments, Stripe session/setup-intent creation, webhooks, access snapshots, and financial reports
- FIFO payment allocation, dues invoice generation, member status enforcement, and basic journal posting
- On-prem access-agent stub under [`onprem/access_agent/`](/home/jpt4/constructs/blbs/membermanagement/onprem/access_agent)
- Docker/Compose scaffolding under [`infra/`](/home/jpt4/constructs/blbs/membermanagement/infra)
- Pytest coverage for the core financial and webhook rules
- Authenticated management API, access-agent key auth for door-access endpoints, and a public [`/healthz`](/home/jpt4/constructs/blbs/membermanagement/backend/config/urls.py) health check

## Local run

1. Install the Python dependencies from [`requirements.txt`](/home/jpt4/constructs/blbs/membermanagement/requirements.txt).
2. Run `PYTHONPATH=.pkg:backend python3 backend/manage.py migrate`
3. Run `PYTHONPATH=.pkg:backend python3 backend/manage.py runserver`
4. Run tests with `PYTHONPATH=.pkg:backend python3 -m pytest -q`

## Deployment

For local development, run the core stack plus [`infra/docker-compose.dev.yml`](/home/jpt4/constructs/blbs/membermanagement/infra/docker-compose.dev.yml).

For the actual Treasurer-facing deployment, run the core stack plus [`infra/docker-compose.prod.yml`](/home/jpt4/constructs/blbs/membermanagement/infra/docker-compose.prod.yml) with [`infra/prod.env.example`](/home/jpt4/constructs/blbs/membermanagement/infra/prod.env.example) as the template for real secrets. The deployment recommendation and rollout steps are in [`docs/qa-hosting.md`](/home/jpt4/constructs/blbs/membermanagement/docs/qa-hosting.md).

## Key assumptions

- The current implementation follows the Django/Postgres spec in `spec.md` and `membermanagement-deep-research-report.md`.
- The shared ChatGPT conversation was not retrievable from this environment, so any requirements unique to that conversation still need to be folded in once you provide accessible text.
