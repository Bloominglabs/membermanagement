# Architecture Notes

## Chosen direction

The repository contained both an older Google Sheets/Apps Script handoff and a newer Django/Postgres spec. This implementation follows the newer Django/Postgres architecture because that is the design repeated across the current payment spec and deep research report.

## Modules

- `apps.members`: clients, members, dues class, lifecycle state
- `apps.billing`: invoices, payments, allocations, processor references, webhook events
- `apps.donations`: Every.org donation ingestion
- `apps.ledger`: lightweight journal and financial report aggregation
- `apps.expenses`: imported expenses and categories
- `apps.access`: RFID credentials, signed allowlist snapshots, access events
- `apps.audit`: append-only audit log

## Current scope

- Stripe-first billing path
- Every.org donation ingestion
- CSV exports and JSON financial report
- Management commands and Celery tasks for dues close, scheduled invoice generation, enforcement, reconciliation reporting, and allowlist refresh
- Thin server-rendered staff operations UI under `/staff/`, alongside Django admin for raw-model access
- On-prem polling agent stub for RFID allowlist sync, kept separate from the public deployment stack

## Known gaps

- Stripe reconciliation and off-session autopay are scaffolded but not yet covered by end-to-end integration tests against Stripe
- The access agent currently caches allowlist snapshots; hardware bridge behavior still needs the actual door-controller protocol
