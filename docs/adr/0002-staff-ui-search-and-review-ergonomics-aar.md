# AAR 0002: Staff UI Search and Review Ergonomics

## Decision Reviewed

[ADR 0002](./0002-staff-ui-search-and-review-ergonomics.md)

## Immediate Outcome

The Staff UI now covers a meaningful portion of the documented parity gap:

- `/staff/search/` provides cross-entity search across members, clients, invoices, payments, and RFID credentials
- member, invoice, and payment review pages now expose explicit sort controls
- invoice and payment review pages now support date-range filtering
- review screens expose direct admin, API, and member-workspace links
- the shared staff header now includes a global-search entry point

## Evidence

- integration coverage was added for cross-entity search, member-list sorting, and billing-review filter/link behavior
- the dedicated Staff UI search/review regression file passes

## Follow-Up

- extend the same escape-hatch treatment to the remaining staff screens such as donations, access, and expense review
- add bulk actions where the workflow justifies them instead of relying on row-by-row operations
- consider whether queue-style saved filters belong on the member and billing review pages
