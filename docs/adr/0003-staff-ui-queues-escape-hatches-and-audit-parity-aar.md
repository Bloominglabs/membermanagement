# AAR 0003: Staff UI Queues, Escape Hatches, and Audit Parity

## Decision Reviewed

[ADR 0003](./0003-staff-ui-queues-escape-hatches-and-audit-parity.md)

## Immediate Outcome

The Staff UI now closes the remaining operational parity gaps identified in the admin UI plan:

- staff home, member review, billing review, and expenses now expose stable queue links for common operational slices
- donation, access, expense, and report pages now expose direct admin, API, and related workflow escape hatches
- invoice review supports bounded bulk issue and void actions
- the audit timeline now supports `entity_id` and date-range filters, and exposes both change summaries and direct entity-admin links

## Evidence

- integration coverage now exercises queue links, bulk invoice actions, support-page escape hatches, and richer audit filtering
- the targeted staff UI suite passes after the new workflow slice

## Follow-Up

- decide whether any additional bulk actions are justified beyond invoice issue and void, rather than adding them speculatively
- keep queue links aligned with real staff use once production patterns become clearer
- revisit whether audit links should eventually include direct workspace links in addition to admin links for more entity types
