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
- Management commands for dues close, enforcement, reconciliation reporting, and allowlist refresh
- On-prem polling agent stub for RFID allowlist sync

## Known gaps

- No real Celery/Redis job worker yet; scheduled work is exposed as management commands and a simple scheduler loop in Compose
- Stripe reconciliation and off-session autopay are scaffolded but not yet covered by end-to-end integration tests against Stripe
- The access agent currently caches allowlist snapshots; hardware bridge behavior still needs the actual door-controller protocol

